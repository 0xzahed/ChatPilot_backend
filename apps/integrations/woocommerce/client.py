"""WooCommerce integration via REST API."""

import httpx
import logging
from django.conf import settings
from ..base.provider import BaseIntegrationProvider, OutgoingResult

logger = logging.getLogger(__name__)


class WooCommerceProvider(BaseIntegrationProvider):
    channel = "woocommerce"

    def is_configured(self) -> bool:
        return bool(self.credentials.get("store_url") and self.credentials.get("consumer_key"))

    def send_message(self, *args, **kwargs) -> OutgoingResult:
        return OutgoingResult(success=True)

    def process_webhook(self, payload: dict, headers: dict) -> list:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/woocommerce/callback?state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {}

    def fetch_products(self) -> list:
        if not self.is_configured():
            return []
        store_url = self.credentials["store_url"]
        key = self.credentials["consumer_key"]
        secret = self.credentials["consumer_secret"]
        url = f"{store_url}/wp-json/wc/v3/products"
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, auth=(key, secret), params={"per_page": 100})
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"WooCommerce fetch products error: {e}")
            return []


class MockWooCommerceProvider(BaseIntegrationProvider):
    channel = "woocommerce"

    def is_configured(self) -> bool:
        return True

    def send_message(self, *args, **kwargs) -> OutgoingResult:
        return OutgoingResult(success=True)

    def process_webhook(self, payload: dict, headers: dict) -> list:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/woocommerce/callback?mock=true&state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {"store_url": "https://demo-store.example.com", "consumer_key": "mock_key", "consumer_secret": "mock_secret"}

    def fetch_products(self) -> list:
        return [
            {"id": 1, "name": "Demo Woo Product 1", "price": "19.99", "sku": "WP-001"},
            {"id": 2, "name": "Demo Woo Product 2", "price": "39.99", "sku": "WP-002"},
        ]


def get_woocommerce_provider(integration=None) -> BaseIntegrationProvider:
    if integration and integration.get_credentials().get("consumer_key"):
        return WooCommerceProvider(integration)
    return MockWooCommerceProvider(integration)
