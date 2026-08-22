"""Facebook Messenger integration provider using Meta Graph API.

Uses the official Meta Graph API for Facebook Pages and Messenger.
When credentials are not available, falls back to MockFacebookProvider
which implements the same interface.
"""

import httpx
import logging
import hashlib
import hmac
import json
from django.conf import settings
from ..base.provider import BaseIntegrationProvider, IncomingMessage, OutgoingResult
from ..base.exceptions import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class FacebookProvider(BaseIntegrationProvider):
    channel = "facebook"

    def is_configured(self) -> bool:
        return bool(self.credentials.get("page_access_token"))

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("Facebook page access token not configured.")

        url = f"{GRAPH_API_BASE}/me/messages"
        params = {"access_token": self.credentials["page_access_token"]}

        if message_type == "text":
            payload = {"recipient": {"id": recipient_id}, "message": {"text": content}}
        elif message_type in ("image", "file"):
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"attachment": {"type": message_type, "payload": {"url": attachment_url}}},
            }
        else:
            payload = {"recipient": {"id": recipient_id}, "message": {"text": content}}

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, params=params, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return OutgoingResult(success=True, external_message_id=data.get("message_id", ""))
        except Exception as e:
            logger.error(f"Facebook send error: {e}")
            return OutgoingResult(success=False, error=str(e))

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        messages = []
        if payload.get("object") != "page":
            return messages

        for entry in payload.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id", "")
                recipient_id = messaging_event.get("recipient", {}).get("id", "")
                message = messaging_event.get("message", {})

                if message and sender_id:
                    msg_type = "text"
                    content = message.get("text", "")
                    attachment_url = ""

                    if "attachments" in message:
                        for att in message["attachments"]:
                            if att.get("type") in ("image", "file", "audio", "video"):
                                msg_type = att["type"]
                                attachment_url = att.get("payload", {}).get("url", "")

                    messages.append(IncomingMessage(
                        external_id=messaging_event.get("message_id", ""),
                        channel="facebook",
                        sender_external_id=sender_id,
                        sender_name="",  # Will be fetched via API
                        content=content,
                        message_type=msg_type,
                        attachment_url=attachment_url,
                        timestamp=messaging_event.get("timestamp", ""),
                        raw_payload=messaging_event,
                    ))

        return messages

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        """Verify the webhook challenge. Meta sends a GET request with hub.challenge."""
        mode = payload.get("hub.mode")
        token = payload.get("hub.verify_token")
        challenge = payload.get("hub.challenge", "")

        if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
            return challenge
        return ""

    def verify_signature(self, payload_body: bytes, signature: str) -> bool:
        """Verify the X-Hub-Signature-256 header."""
        if not settings.META_APP_SECRET:
            return True  # Skip if not configured
        expected = "sha256=" + hmac.new(
            settings.META_APP_SECRET.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return (
            f"https://www.facebook.com/v20.0/dialog/oauth"
            f"?client_id={settings.META_APP_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope=pages_messaging,pages_manage_posts,pages_read_engagement"
        )

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        """Exchange OAuth code for access token, then get page access token."""
        url = f"{GRAPH_API_BASE}/oauth/access_token"
        params = {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                user_token = data["access_token"]

                # Get pages
                pages_url = f"{GRAPH_API_BASE}/me/accounts"
                pages_resp = client.get(pages_url, params={"access_token": user_token})
                pages_resp.raise_for_status()
                pages_data = pages_resp.json()

                if pages_data.get("data"):
                    page = pages_data["data"][0]
                    return {
                        "page_id": page["id"],
                        "page_name": page["name"],
                        "page_access_token": page["access_token"],
                    }
                return {}
        except Exception as e:
            logger.error(f"Facebook OAuth error: {e}")
            return {}


class MockFacebookProvider(BaseIntegrationProvider):
    """Mock Facebook provider for development without Meta credentials."""

    channel = "facebook"

    def is_configured(self) -> bool:
        return True

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        logger.info(f"[MockFacebook] Sending message to {recipient_id}: {content[:50]}")
        return OutgoingResult(success=True, external_message_id=f"mock_fb_msg_{hash(content) & 0xFFFFFF}")

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        # In mock mode, webhooks are simulated via the webchat/testing interface
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        mode = payload.get("hub.mode")
        token = payload.get("hub.verify_token")
        if mode == "subscribe" and token == settings.META_VERIFY_TOKEN:
            return payload.get("hub.challenge", "")
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/facebook/callback?mock=true&state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {
            "page_id": "mock_page_123",
            "page_name": "Demo Business Page",
            "page_access_token": "mock_page_token_abc123",
        }


def get_facebook_provider(integration=None) -> BaseIntegrationProvider:
    """Return real or mock provider based on configuration."""
    if integration and integration.get_credentials().get("page_access_token"):
        return FacebookProvider(integration)
    if settings.META_APP_ID and settings.META_APP_SECRET:
        return FacebookProvider(integration)
    return MockFacebookProvider(integration)
