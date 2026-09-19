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
            workspace=event.workspace, integration_type=source, is_active=True
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

        for incoming in incoming_messages:
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

            # Update conversation
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = incoming.content[:100]
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
