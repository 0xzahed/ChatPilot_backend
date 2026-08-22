from django.urls import path
from .webhooks import FacebookWebhookView

urlpatterns = [
    path("", FacebookWebhookView.as_view(), name="facebook-webhook"),
]
