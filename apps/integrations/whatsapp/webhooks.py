import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.integrations.models import WebhookEvent
from apps.integrations.whatsapp.client import get_whatsapp_provider

logger = logging.getLogger(__name__)


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
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        webhook_event = WebhookEvent.objects.create(
            source="whatsapp",
            event_type="message",
            payload=payload,
        )
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(webhook_event.id), "whatsapp")
        return JsonResponse({"status": "received"})
