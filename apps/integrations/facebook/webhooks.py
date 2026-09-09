import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent, Integration
from apps.integrations.facebook.client import get_facebook_provider
from common.api_response import api_error, api_success, api_paginated

logger = logging.getLogger(__name__)


def _get_facebook_integration():
    """Find the active Facebook integration (any workspace)."""
    return Integration.objects.filter(
        integration_type="facebook", is_active=True, status="connected"
    ).first()


@method_decorator(csrf_exempt, name="dispatch")
class FacebookWebhookView(View):
    """Facebook/Meta webhook endpoint for Messenger and Instagram."""

    def get(self, request):
        """Webhook verification challenge."""
        integration = _get_facebook_integration()
        provider = get_facebook_provider(integration)
        challenge = provider.verify_webhook(
            {"hub.mode": request.GET.get("hub.mode"),
             "hub.verify_token": request.GET.get("hub.verify_token"),
             "hub.challenge": request.GET.get("hub.challenge", "")},
            dict(request.headers),
        )
        if challenge:
            return HttpResponse(challenge)
        return HttpResponse("Verification failed", status=403)

    def post(self, request):
        """Incoming webhook event from Meta."""
        body = request.body
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON", "code": "BAD_REQUEST"}, status=400)

        integration = _get_facebook_integration()

        # Store webhook event for idempotency and replay
        external_id = payload.get("entry", [{}])[0].get("id", "") if payload.get("entry") else ""
        webhook_event = WebhookEvent.objects.create(
            workspace=integration.workspace if integration else None,
            source="facebook",
            event_type=payload.get("object", ""),
            external_id=external_id,
            payload=payload,
            signature=request.headers.get("X-Hub-Signature-256", ""),
        )

        # Process with provider
        provider = get_facebook_provider(integration)
        messages = provider.process_webhook(payload, dict(request.headers))

        # Process synchronously (no Celery available) — run the task logic directly
        try:
            _process_webhook_sync(webhook_event, integration, "facebook")
        except Exception as e:
            logger.error(f"Webhook sync processing error: {e}")

        return JsonResponse({"status": "received", "messages": len(messages)})


def _process_webhook_sync(webhook_event, integration, source):
    """Process incoming webhook messages synchronously (no Celery)."""
    from apps.customers.models import Customer, CustomerChannel
    from apps.inbox.models import Conversation, Message
    from apps.inbox.consumers import broadcast_new_message, broadcast_workspace_event
    from django.utils import timezone

    webhook_event.status = "processing"
    webhook_event.attempts += 1
    webhook_event.save(update_fields=["status", "attempts"])

    try:
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
            webhook_event.status = "processed"
            webhook_event.processed_at = timezone.now()
            webhook_event.save()
            return

        incoming_messages = provider.process_webhook(webhook_event.payload, {})
        workspace = integration.workspace if integration else webhook_event.workspace

        # Fetch sender names from Graph API for Facebook
        if source == "facebook" and incoming_messages:
            try:
                _enrich_sender_names(provider, incoming_messages)
            except Exception as e:
                logger.warning(f"Failed to enrich sender names: {e}")

        for incoming in incoming_messages:
            # Skip empty messages (no text and no attachment)
            if not incoming.content and not incoming.attachment_url:
                continue

            # Find or create customer
            customer_channel = CustomerChannel.objects.filter(
                channel=incoming.channel, external_id=incoming.sender_external_id
            ).first()

            if customer_channel:
                customer = customer_channel.customer
                # Update name if we now have it
                if incoming.sender_name and customer.name == "Unknown Customer":
                    customer.name = incoming.sender_name
                    customer.save(update_fields=["name"])
                    customer_channel.display_name = incoming.sender_name
                    customer_channel.save(update_fields=["display_name"])
                # Update profile pic if we have it
                if incoming.sender_pic and not customer_channel.profile_url:
                    customer_channel.profile_url = incoming.sender_pic
                    customer_channel.save(update_fields=["profile_url"])
            else:
                if not workspace:
                    workspace = integration.workspace if integration else None
                if not workspace:
                    continue
                customer = Customer.objects.create(
                    workspace=workspace,
                    name=incoming.sender_name or "Unknown Customer",
                )
                CustomerChannel.objects.create(
                    customer=customer,
                    channel=incoming.channel,
                    external_id=incoming.sender_external_id,
                    display_name=incoming.sender_name,
                    profile_url=incoming.sender_pic,
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

            # Save page_id in conversation config for replies
            if incoming.page_id:
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

            # Update conversation
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = incoming.content[:100]
            conversation.unread_count += 1
            conversation.save(update_fields=["last_message_at", "last_message_preview", "unread_count"])

            # Broadcast via WebSocket
            try:
                broadcast_new_message(message)
                broadcast_workspace_event(customer.workspace_id, "new_message", {
                    "conversation_id": str(conversation.id),
                    "channel": incoming.channel,
                })
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed: {e}")

            # Trigger AI if enabled
            if conversation.ai_enabled:
                try:
                    from apps.ai.services.ai_service import AIService
                    ai_service = AIService(customer.workspace)
                    if ai_service.settings.mode in ("auto_reply", "hybrid"):
                        ai_service.auto_reply(conversation, message)
                except Exception as e:
                    logger.warning(f"AI auto-reply failed: {e}")

        webhook_event.status = "processed"
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at"])

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        webhook_event.status = "failed"
        webhook_event.error_message = str(e)
        webhook_event.save(update_fields=["status", "error_message"])


def _enrich_sender_names(provider, messages):
    """Fetch sender names and profile pictures from Facebook Graph API."""
    import httpx
    from apps.integrations.models import Integration

    integration = Integration.objects.filter(
        integration_type="facebook", is_active=True, status="connected"
    ).first()
    if not integration:
        return

    creds = integration.get_credentials()
    pages = creds.get("pages", [])
    page_token = pages[0].get("page_access_token", "") if pages else creds.get("page_access_token", "")
    if not page_token:
        return

    # Collect unique sender IDs
    sender_ids = set()
    for msg in messages:
        if msg.sender_external_id:
            sender_ids.add(msg.sender_external_id)

    # Fetch names + profile pics in batch
    with httpx.Client(timeout=10) as client:
        for sid in sender_ids:
            try:
                resp = client.get(
                    f"https://graph.facebook.com/v20.0/{sid}",
                    params={"access_token": page_token, "fields": "name,first_name,last_name,picture{url}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    name = data.get("name", "")
                    pic_url = data.get("picture", {}).get("data", {}).get("url", "")
                    for msg in messages:
                        if msg.sender_external_id == sid:
                            if name:
                                msg.sender_name = name
                            if pic_url:
                                msg.sender_pic = pic_url
            except Exception as e:
                logger.warning(f"Failed to fetch name for sender {sid}: {e}")
