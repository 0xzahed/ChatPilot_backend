import json
import hmac
import hashlib
import logging
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent
from apps.integrations.whatsapp.client import get_whatsapp_provider
from common.api_response import api_error, api_success, api_paginated

logger = logging.getLogger(__name__)


def _verify_hub_signature(body: bytes, signature_header: str, app_secret: str) -> bool:
    """Verify X-Hub-Signature-256 header for Meta/WhatsApp webhooks.

    The header format is: sha256=<hex_digest>
    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature_header or not app_secret:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_sig = signature_header[7:]  # strip "sha256=" prefix
    computed = hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected_sig)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):
    def get(self, request):
        provider = get_whatsapp_provider()
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
        # Verify webhook signature BEFORE processing
        app_secret = getattr(settings, "META_APP_SECRET", "")
        if not app_secret:
            logger.error("META_APP_SECRET is not configured — rejecting WhatsApp webhook")
            return JsonResponse(
                {"success": False, "message": "Webhook verification not configured", "code": "CONFIG_ERROR"},
                status=500,
            )

        raw_body = request.body
        signature = request.headers.get("X-Hub-Signature-256", "")

        if not _verify_hub_signature(raw_body, signature, app_secret):
            logger.warning("WhatsApp webhook signature verification failed")
            return JsonResponse(
                {"success": False, "message": "Invalid signature", "code": "INVALID_SIGNATURE"},
                status=403,
            )

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON", "code": "BAD_REQUEST"}, status=400)

        webhook_event = WebhookEvent.objects.create(
            source="whatsapp",
            event_type="message",
            payload=payload,
            signature=signature,
        )
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(webhook_event.id), "whatsapp")
        return JsonResponse({"status": "received"})
