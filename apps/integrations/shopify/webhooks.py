import json
import hmac
import hashlib
import base64
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent
from common.api_response import api_error, api_success, api_paginated

logger = logging.getLogger(__name__)


def _verify_shopify_hmac(body: bytes, signature: str, secret: str) -> bool:
    """Verify the Shopify HMAC-SHA256 signature against the raw request body.

    Shopify sends the HMAC as a base64-encoded string in X-Shopify-Hmac-Sha256.
    We compute our own HMAC and compare using constant-time comparison.
    """
    if not signature or not secret:
        return False
    computed = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyWebhookView(View):
    def post(self, request):
        # Verify HMAC signature BEFORE processing the payload
        shopify_secret = getattr(settings, "SHOPIFY_WEBHOOK_SECRET", "")
        if not shopify_secret:
            logger.error("SHOPIFY_WEBHOOK_SECRET is not configured — rejecting webhook")
            return JsonResponse(
                {"success": False, "message": "Webhook verification not configured", "code": "CONFIG_ERROR"},
                status=500,
            )

        signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
        raw_body = request.body

        if not _verify_shopify_hmac(raw_body, signature, shopify_secret):
            logger.warning("Shopify webhook HMAC verification failed")
            return JsonResponse(
                {"success": False, "message": "Invalid signature", "code": "INVALID_SIGNATURE"},
                status=403,
            )

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON", "code": "BAD_REQUEST"}, status=400)

        topic = request.headers.get("X-Shopify-Topic", "unknown")
        webhook_event = WebhookEvent.objects.create(
            source="shopify",
            event_type=topic,
            payload=payload,
            signature=signature,
        )
        from apps.integrations.shopify.tasks import sync_shopify_webhook
        sync_shopify_webhook.delay(str(webhook_event.id))
        return JsonResponse({"status": "received"})
