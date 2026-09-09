import json
import logging
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent
from common.api_response import api_error, api_success, api_paginated

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyWebhookView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON", "code": "BAD_REQUEST"}, status=400)

        topic = request.headers.get("X-Shopify-Topic", "unknown")
        webhook_event = WebhookEvent.objects.create(
            source="shopify",
            event_type=topic,
            payload=payload,
        )
        from apps.integrations.shopify.tasks import sync_shopify_webhook
        sync_shopify_webhook.delay(str(webhook_event.id))
        return JsonResponse({"status": "received"})
