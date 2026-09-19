"""Map iedu support-chat objects into ChatPilot models.

Bridged conversations are stored as channel="website" conversations tagged
with config.bridge="iedu" and external_id="iedu_<iedu conv id>". Messages are
deduplicated via external_id="iedu_msg_<iedu msg id>".
"""
import logging

from django.utils import timezone

from apps.customers.models import Customer, CustomerChannel
from apps.inbox.models import Conversation, Message

logger = logging.getLogger(__name__)


def ensure_customer(workspace, iedu_conv):
    """Return the ChatPilot Customer for this iedu conversation's user."""
    user = iedu_conv.get("user") or {}
    user_id = user.get("id") or iedu_conv.get("facebook_psid") or iedu_conv.get("id")
    external_id = f"iedu_user_{user_id}"
    channel = CustomerChannel.objects.filter(
        channel="website", external_id=external_id
    ).first()
    if channel:
        return channel.customer

    name = (
        iedu_conv.get("display_name")
        or user.get("username")
        or iedu_conv.get("guest_name")
        or "iedu User"
    )
    customer = Customer.objects.create(
        workspace=workspace,
        name=name,
        phone=iedu_conv.get("guest_phone") or "",
    )
    CustomerChannel.objects.create(
        customer=customer,
        channel="website",
        external_id=external_id,
        display_name=name,
    )
    return customer


def ensure_conversation(workspace, iedu_conv):
    """Return (Conversation, created) for an iedu conversation."""
    conv = Conversation.objects.filter(
        workspace=workspace, external_id=f"iedu_{iedu_conv['id']}"
    ).first()
    if conv:
        return conv, False

    customer = ensure_customer(workspace, iedu_conv)
    conv = Conversation.objects.create(
        workspace=workspace,
        customer=customer,
        channel="website",
        status="open",
        handled_by="unassigned",
        external_id=f"iedu_{iedu_conv['id']}",
        config={"bridge": "iedu"},
        ai_enabled=False,
        last_message_at=timezone.now(),
        last_message_preview=iedu_conv.get("last_message_preview") or "",
    )
    return conv, True


def _iedu_sender_id(m):
    sender = m.get("sender")
    if isinstance(sender, dict):
        return sender.get("id")
    return sender


def _iedu_sender_name(m):
    sender = m.get("sender")
    if isinstance(sender, dict):
        return sender.get("name") or sender.get("username") or ""
    return m.get("user_name") or ""


def mirror_messages(workspace, conv, iedu_messages, bridge_user_id=None):
    """Create ChatPilot Messages for unseen iedu messages.

    - sender_type=="user"  → inbound customer message
    - sender_type=="staff" → outbound agent/AI message, EXCEPT messages sent
      by the bridge account itself (prevents echo loops)
    """
    created = []
    # iedu returns newest-first — mirror oldest-first for correct ordering
    ordered = sorted(iedu_messages, key=lambda m: m.get("created_at") or "")
    for m in ordered:
        st = m.get("sender_type")
        if st not in ("user", "staff"):
            continue
        if st == "staff" and bridge_user_id and _iedu_sender_id(m) == bridge_user_id:
            continue
        ext_id = f"iedu_msg_{m['id']}"
        if Message.objects.filter(external_id=ext_id).exists():
            continue
        content = (m.get("content") or "").strip()
        if not content and m.get("file_url"):
            content = f"[Attachment] {m.get('file_name') or ''} {m['file_url']}".strip()
        if not content:
            continue

        if st == "user":
            sender_type, direction, status = "customer", "inbound", "sent"
            meta = {}
        else:
            sender_type = "ai" if m.get("is_ai_generated") else "agent"
            direction, status = "outbound", "delivered"
            meta = {"iedu_sender": _iedu_sender_name(m)}

        msg = Message.objects.create(
            conversation=conv,
            workspace=workspace,
            sender_type=sender_type,
            direction=direction,
            message_type="text",
            content=content[:5000],
            external_id=ext_id,
            status=status,
            ai_metadata=meta,
        )
        created.append(msg)
    return created


def sync_conversation(workspace, iedu_conv, iedu_messages, bridge_user_id=None):
    """Mirror one iedu conversation + its new inbound messages into ChatPilot."""
    from apps.inbox.consumers import (
        broadcast_new_message,
        broadcast_conversation_update,
        broadcast_workspace_event,
    )

    conv, _ = ensure_conversation(workspace, iedu_conv)

    # iedu → ChatPilot status sync (admin actions in iedu panel reflect here)
    _STATUS_REVERSE = {
        "open": "open",
        "follow_up": "pending",
        "done": "closed",
        "archived": "closed",
        "spam": "closed",
    }
    iedu_status = _STATUS_REVERSE.get(iedu_conv.get("status"))
    if iedu_status and conv.status != iedu_status:
        conv.status = iedu_status
        conv.save(update_fields=["status"])

    new_msgs = mirror_messages(workspace, conv, iedu_messages, bridge_user_id)
    if not new_msgs:
        return conv, []

    last = new_msgs[-1]
    conv.last_message_at = timezone.now()
    conv.last_message_preview = last.content[:100]
    conv.unread_count += sum(1 for m in new_msgs if m.direction == "inbound")
    conv.save(
        update_fields=["last_message_at", "last_message_preview", "unread_count"]
    )

    try:
        for msg in new_msgs:
            broadcast_new_message(msg)
        broadcast_conversation_update(conv)
        broadcast_workspace_event(
            str(workspace.id),
            "new_message",
            {"conversation_id": str(conv.id), "channel": "website"},
        )
    except Exception:
        # Data is already persisted — a broadcast hiccup only delays the
        # live UI update until the next event/refetch.
        logger.exception("[iedu-bridge] broadcast failed")
    return conv, new_msgs
