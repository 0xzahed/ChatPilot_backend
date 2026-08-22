import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent
from apps.integrations.facebook.client import get_facebook_provider

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class FacebookWebhookView(View):
    """Facebook/Meta webhook endpoint for Messenger and Instagram."""

    def get(self, request):
        """Webhook verification challenge."""
        provider = get_facebook_provider()
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
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Store webhook event for idempotency and replay
        external_id = payload.get("entry", [{}])[0].get("id", "") if payload.get("entry") else ""
        webhook_event = WebhookEvent.objects.create(
            source="facebook",
            event_type=payload.get("object", ""),
            external_id=external_id,
            payload=payload,
            signature=request.headers.get("X-Hub-Signature-256", ""),
        )

        # Process with provider
        provider = get_facebook_provider()
        messages = provider.process_webhook(payload, dict(request.headers))

        # Queue for processing
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(webhook_event.id), "facebook")

        return JsonResponse({"status": "received", "messages": len(messages)})
