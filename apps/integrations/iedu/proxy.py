"""Live proxy: serve iedu support-chat data without local DB storage.

iedu conversations/messages are transformed into ChatPilot response shapes on
the fly. Pseudo-ids (`iedu_<pk>` / `iedu_msg_<pk>`) let the frontend treat them
as regular conversations while every read/write goes straight to iedu's API.
"""
import logging

from .client import get_iedu_client

logger = logging.getLogger(__name__)

# iedu SupportConversation.status → ChatPilot Conversation.status
STATUS_TO_CP = {
    "open": "open",
    "follow_up": "pending",
    "done": "closed",
    "archived": "closed",
    "spam": "closed",
}

MSG_TYPE_TO_CP = {
    "Text": "text",
    "Image": "image",
    "File": "file",
    "Audio": "audio",
    "Video": "video",
    "System": "system",
    "Note": "note",
}


def is_iedu_id(value):
    return str(value).startswith("iedu_")


def iedu_pk(value):
    return str(value).removeprefix("iedu_")


def client_for_user(user):
    """First workspace of this user that has an active iedu integration."""
    from apps.inbox.views import get_user_workspaces
    from apps.integrations.models import Integration

    ws_ids = get_user_workspaces(user)
    integration = Integration.objects.filter(
        workspace_id__in=ws_ids,
        integration_type="website",
        is_active=True,
        config__bridge="iedu",
    ).first()
    if not integration:
        return None
    return get_iedu_client(integration.workspace)


def _label_dict(l):
    if isinstance(l, dict):
        name = l.get("name") or l.get("title") or str(l.get("id") or "")
        return {"id": str(l.get("id") or name), "name": name, "color": "blue", "created_at": None}
    return {"id": str(l), "name": str(l), "color": "blue", "created_at": None}


def conv_to_cp(c):
    user = c.get("user") or {}
    assigned = c.get("assigned_to")
    return {
        "id": f"iedu_{c['id']}",
        "customer": None,
        "customer_name": c.get("display_name") or user.get("username") or c.get("guest_name") or "iedu User",
        "customer_avatar": c.get("customer_profile_pic") or None,
        "customer_phone": c.get("guest_phone") or user.get("mobile") or "",
        "channel": "website",
        "channel_icon": "website",
        "status": STATUS_TO_CP.get(c.get("status"), "open"),
        "handled_by": "unassigned",
        "assigned_to": None,
        "assigned_to_name": (assigned or {}).get("name") or (assigned or {}).get("username") if isinstance(assigned, dict) else None,
        "labels": [_label_dict(l) for l in (c.get("labels") or [])],
        "last_message_at": c.get("last_message_at"),
        "last_message_preview": c.get("last_message_preview") or "",
        "unread_count": c.get("unread_count") or 0,
        "is_complaint": False,
        "has_order": False,
        "ai_enabled": False,
        "language": "en",
        "page_name": None,
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "external_id": f"iedu_{c['id']}",
    }


def _sender_name(m):
    sender = m.get("sender")
    if isinstance(sender, dict):
        return sender.get("name") or sender.get("username") or ""
    return m.get("user_name") or ""


def msg_to_cp(m, conv_pk):
    st = m.get("sender_type")
    if st == "staff":
        sender_type = "ai" if m.get("is_ai_generated") else "agent"
        direction = "outbound"
    else:
        sender_type, direction = "customer", "inbound"

    attachments = []
    if m.get("file_url"):
        attachments.append({
            "id": f"iedu_att_{m['id']}",
            "file_url": m["file_url"],
            "file_name": m.get("file_name") or "",
            "file_type": (m.get("message_type") or "File").lower(),
            "file_size": None,
            "mime_type": None,
            "created_at": m.get("created_at"),
        })

    return {
        "id": f"iedu_msg_{m['id']}",
        "conversation": f"iedu_{conv_pk}",
        "sender_type": sender_type,
        "direction": direction,
        "message_type": MSG_TYPE_TO_CP.get(m.get("message_type"), "text"),
        "content": m.get("content") or "",
        "status": "delivered",
        "attachments": attachments,
        "sender_name": _sender_name(m) or m.get("user_name") or ("Customer" if st == "user" else "Staff"),
        "sent_by": None,
        "reply_to": None,
        "ai_metadata": {"iedu_sender": _sender_name(m)} if st == "staff" else {},
        "is_read": True,
        "created_at": m.get("created_at"),
        "updated_at": m.get("created_at"),
    }


def list_conversations(client, page=1, limit=30, search="", status="", unread=False):
    """Fetch a page of iedu conversations, transformed to ChatPilot shape."""
    params = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    data = client._request("GET", "/support/admin/conversations", params=params)
    items = [conv_to_cp(c) for c in (data.get("data") or [])]
    if status:
        items = [c for c in items if c["status"] == status]
    if unread:
        items = [c for c in items if c["unread_count"] > 0]
    return items, data


def get_detail(client, conv_pk, limit=100):
    """Return (conversation_dict, [message_dicts oldest-first])."""
    conv, msgs = client.get_messages(conv_pk, limit=limit)
    ordered = sorted(msgs, key=lambda m: m.get("created_at") or "")
    return conv_to_cp(conv) if conv else None, [msg_to_cp(m, conv_pk) for m in ordered]
