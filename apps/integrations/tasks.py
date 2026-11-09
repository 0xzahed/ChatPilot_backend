from celery import shared_task
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def process_incoming_messages(webhook_event_id, source):
    """Process incoming messages from a webhook event."""
    from apps.integrations.models import WebhookEvent, Integration
    from apps.customers.models import Customer, CustomerChannel
    from apps.inbox.models import Conversation, Message
    from apps.inbox.consumers import broadcast_new_message, broadcast_workspace_event

    event = WebhookEvent.objects.filter(id=webhook_event_id).first()
    if not event:
        return

    event.status = "processing"
    event.attempts += 1
    event.save(update_fields=["status", "attempts"])

    try:
        # Get the provider for this source
        integration = Integration.objects.filter(
            workspace=event.workspace, integration_type=source, is_active=True, status="connected"
        ).first() if event.workspace else None

        if source == "facebook":
            from apps.integrations.facebook.client import get_facebook_provider
            provider = get_facebook_provider(integration)
        elif source == "instagram":
            from apps.integrations.instagram.client import get_instagram_provider
            provider = get_instagram_provider(integration)
        elif source == "whatsapp":
            from apps.integrations.whatsapp.client import get_whatsapp_provider
            provider = get_whatsapp_provider(integration)
        else:
            event.status = "processed"
            event.processed_at = timezone.now()
            event.save()
            return

        incoming_messages = provider.process_webhook(event.payload, {})

        # Fetch sender names from the Graph API for Facebook (same as the
        # synchronous webhook path) so customers don't show as "Unknown".
        if source == "facebook" and incoming_messages:
            try:
                from apps.integrations.facebook.inbound import enrich_senders
                enrich_senders(incoming_messages)
            except Exception as enrich_err:
                logger.warning(f"Failed to enrich sender names: {enrich_err}")

        for incoming in incoming_messages:
            # Skip empty messages (no text and no attachment)
            if not incoming.content and not getattr(incoming, "attachment_url", "") and not getattr(incoming, "attachments", None):
                continue

            # Find or create customer (scoped to workspace)
            workspace = event.workspace
            if not workspace and integration:
                workspace = integration.workspace
            if not workspace:
                continue

            customer_channel = CustomerChannel.objects.filter(
                workspace=workspace, channel=incoming.channel, external_id=incoming.sender_external_id
            ).first()

            if customer_channel:
                customer = customer_channel.customer
                if source == "facebook":
                    from apps.integrations.facebook.inbound import apply_sender_profile
                    apply_sender_profile(customer, customer_channel, incoming)
            else:
                customer = Customer.objects.create(
                    workspace=workspace,
                    name=incoming.sender_name or "Unknown Customer",
                )
                CustomerChannel.objects.create(
                    customer=customer,
                    workspace=workspace,
                    channel=incoming.channel,
                    external_id=incoming.sender_external_id,
                    display_name=incoming.sender_name,
                    profile_url=getattr(incoming, "sender_pic", "") or "",
                )

            # Find or create conversation
            conversation = Conversation.objects.filter(
                customer=customer, channel=incoming.channel, status="open"
            ).first()

            if not conversation:
                conversation = Conversation.objects.create(
                    workspace=customer.workspace,
                    customer=customer,
                    channel=incoming.channel,
                    external_id=incoming.external_id,
                )

            # Save page_id in conversation config — the inbox hides Facebook
            # conversations without it, and replies need it to pick the Page.
            if getattr(incoming, "page_id", ""):
                conversation.config["page_id"] = incoming.page_id
                conversation.save(update_fields=["config"])

            # Skip duplicate messages
            if incoming.external_id and Message.objects.filter(external_id=incoming.external_id).exists():
                continue

            # Create message
            message = Message.objects.create(
                conversation=conversation,
                workspace=customer.workspace,
                sender_type="customer",
                direction="inbound",
                message_type=incoming.message_type,
                content=incoming.content,
                external_id=incoming.external_id,
                status="sent",
            )

            # Store incoming media (image / voice / video / file) locally
            if getattr(incoming, "attachments", None):
                from apps.integrations.facebook.inbound import save_incoming_attachments
                save_incoming_attachments(message, incoming)

            # Update conversation
            from apps.integrations.facebook.inbound import preview_for
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = preview_for(incoming)
            conversation.unread_count += 1
            conversation.save(update_fields=["last_message_at", "last_message_preview", "unread_count"])

            # Broadcast
            broadcast_new_message(message)
            broadcast_workspace_event(customer.workspace_id, "new_message", {
                "conversation_id": str(conversation.id),
            })

            # Trigger AI if enabled
            if conversation.ai_enabled:
                from apps.ai.services.ai_service import AIService
                ai_service = AIService(customer.workspace)
                if ai_service.settings.mode in ("auto_reply", "hybrid"):
                    ai_service.auto_reply(conversation, message)

        event.status = "processed"
        event.processed_at = timezone.now()

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        event.status = "failed"
        event.error_message = str(e)
        if event.attempts >= 3:
            event.status = "dead_letter"

    event.save()


@shared_task
def auto_sync_facebook_integrations():
    """Periodic safety-net sync for every connected Facebook integration.

    Real-time delivery goes through the webhook; this just catches anything
    missed (e.g. a webhook delivery that failed) so the inbox self-heals
    without someone needing to click the manual Sync button.
    """
    from apps.integrations.models import Integration
    from apps.integrations.views import sync_facebook_historical_data

    integrations = Integration.objects.filter(
        integration_type="facebook", is_active=True, status="connected"
    )
    for integration in integrations:
        try:
            result = sync_facebook_historical_data(integration)
            if result:
                logger.info(
                    f"Auto-sync facebook integration {integration.id}: "
                    f"{result['synced_convs']} new conversations, {result['synced_msgs']} new messages"
                )
        except Exception as e:
            logger.error(f"Auto-sync failed for facebook integration {integration.id}: {e}")


@shared_task
def mark_facebook_seen(conversation_id):
    """Show "Seen" to the customer on Messenger once an agent opens the chat."""
    from apps.customers.models import CustomerChannel
    from apps.inbox.models import Conversation
    from apps.integrations.models import Integration
    from apps.integrations.facebook.client import get_facebook_provider

    conv = Conversation.objects.filter(id=conversation_id, channel="facebook").select_related("customer").first()
    if not conv:
        return
    cc = CustomerChannel.objects.filter(customer=conv.customer, channel="facebook").first()
    page_id = (conv.config or {}).get("page_id", "")
    if not cc or not page_id:
        return
    for integ in Integration.objects.filter(
        workspace=conv.workspace, integration_type="facebook", is_active=True, status="connected"
    ).order_by("-created_at"):
        if any(p.get("page_id") == page_id for p in integ.get_credentials().get("pages", [])):
            provider = get_facebook_provider(integ)
            if hasattr(provider, "mark_seen"):
                provider.mark_seen(cc.external_id, page_id)
            return
