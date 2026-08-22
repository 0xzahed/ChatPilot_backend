from django.urls import path
from .webhooks import ShopifyWebhookView

urlpatterns = [
    path("", ShopifyWebhookView.as_view(), name="shopify-webhook"),
]
