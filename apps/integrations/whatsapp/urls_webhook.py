from django.urls import path
from .webhooks import WhatsAppWebhookView

urlpatterns = [
    path("", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
]
