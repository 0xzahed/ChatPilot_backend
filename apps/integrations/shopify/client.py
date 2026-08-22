"""Shopify integration for product/order sync."""

import httpx
import logging
import hashlib
import hmac
from django.conf import settings
from ..base.provider import BaseIntegrationProvider, OutgoingResult

logger = logging.getLogger(__name__)


class ShopifyProvider(BaseIntegrationProvider):
    channel = "shopify"

    def is_configured(self) -> bool:
        return bool(self.credentials.get("shop_domain") and self.credentials.get("access_token"))

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        return OutgoingResult(success=True, external_message_id="shopify_n/a")

    def process_webhook(self, payload: dict, headers: dict) -> list:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        return ""

    def verify_signature(self, payload_body: bytes, signature: str) -> bool:
        if not settings.SHOPIFY_API_SECRET:
            return True
        computed = hmac.new(
            settings.SHOPIFY_API_SECRET.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, signature)

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        shop_domain = self.credentials.get("shop_domain", "")
        if not shop_domain:
            return ""
        return (
            f"https://{shop_domain}/admin/oauth/authorize"
            f"?client_id={settings.SHOPIFY_API_KEY}"
            f"&scope=read_products,write_products,read_orders,write_orders"
            f"&redirect_uri={redirect_uri}&state={state}"
        )

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        shop_domain = self.credentials.get("shop_domain", "")
        url = f"https://{shop_domain}/admin/oauth/access_token"
        payload = {
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "code": code,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Shopify OAuth error: {e}")
            return {}

    def fetch_products(self) -> list:
        """Fetch products from Shopify."""
        if not self.is_configured():
            return []
        shop_domain = self.credentials["shop_domain"]
        token = self.credentials["access_token"]
        url = f"https://{shop_domain}/admin/api/2024-01/products.json"
        headers = {"X-Shopify-Access-Token": token}
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json().get("products", [])
        except Exception as e:
            logger.error(f"Shopify fetch products error: {e}")
            return []

    def fetch_orders(self) -> list:
        if not self.is_configured():
            return []
        shop_domain = self.credentials["shop_domain"]
        token = self.credentials["access_token"]
        url = f"https://{shop_domain}/admin/api/2024-01/orders.json"
        headers = {"X-Shopify-Access-Token": token}
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json().get("orders", [])
        except Exception as e:
            logger.error(f"Shopify fetch orders error: {e}")
            return []


class MockShopifyProvider(BaseIntegrationProvider):
    channel = "shopify"

    def is_configured(self) -> bool:
        return True

    def send_message(self, *args, **kwargs) -> OutgoingResult:
        return OutgoingResult(success=True)

    def process_webhook(self, payload: dict, headers: dict) -> list:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/shopify/callback?mock=true&state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {"shop_domain": "demo-shop.myshopify.com", "access_token": "mock_shopify_token"}

    def fetch_products(self) -> list:
        return [
            {"id": 1, "title": "Demo Shopify Product 1", "variants": [{"price": "29.99", "sku": "SP-001"}]},
            {"id": 2, "title": "Demo Shopify Product 2", "variants": [{"price": "49.99", "sku": "SP-002"}]},
        ]

    def fetch_orders(self) -> list:
        return []


def get_shopify_provider(integration=None) -> BaseIntegrationProvider:
    if integration and integration.get_credentials().get("access_token"):
        return ShopifyProvider(integration)
    if settings.SHOPIFY_API_KEY and settings.SHOPIFY_API_SECRET:
        return ShopifyProvider(integration)
    return MockShopifyProvider(integration)
