"""Instagram Business/Creator integration via Meta Graph API.

Instagram messaging uses the same Meta webhook infrastructure as Facebook
Messenger, but with Instagram-specific endpoints.
"""

import httpx
import logging
from django.conf import settings
from ..base.provider import BaseIntegrationProvider, IncomingMessage, OutgoingResult
from ..base.exceptions import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)
GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class InstagramProvider(BaseIntegrationProvider):
    channel = "instagram"

    def is_configured(self) -> bool:
        return bool(self.credentials.get("instagram_access_token"))

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("Instagram access token not configured.")

        url = f"{GRAPH_API_BASE}/me/messages"
        params = {"access_token": self.credentials["instagram_access_token"]}
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": content} if message_type == "text" else {
                "attachment": {"type": message_type, "payload": {"url": attachment_url}}
            },
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, params=params, json=payload)
                resp.raise_for_status()
                return OutgoingResult(success=True, external_message_id=resp.json().get("message_id", ""))
        except Exception as e:
            logger.error(f"Instagram send error: {e}")
            return OutgoingResult(success=False, error=str(e))

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        messages = []
        if payload.get("object") != "instagram":
            return messages

        for entry in payload.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id", "")
                message = messaging_event.get("message", {})
                if message and sender_id:
                    messages.append(IncomingMessage(
                        external_id=messaging_event.get("message_id", ""),
                        channel="instagram",
                        sender_external_id=sender_id,
                        sender_name="",
                        content=message.get("text", ""),
                        message_type="text",
                        timestamp=messaging_event.get("timestamp", ""),
                        raw_payload=messaging_event,
                    ))
        return messages

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        if payload.get("hub.mode") == "subscribe" and payload.get("hub.verify_token") == settings.META_VERIFY_TOKEN:
            return payload.get("hub.challenge", "")
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return (
            f"https://www.facebook.com/v20.0/dialog/oauth"
            f"?client_id={settings.META_APP_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_manage_messages,instagram_manage_comments"
        )

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        url = f"{GRAPH_API_BASE}/oauth/access_token"
        params = {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": redirect_uri, "code": code,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return {"instagram_access_token": data["access_token"]}
        except Exception as e:
            logger.error(f"Instagram OAuth error: {e}")
            return {}


class MockInstagramProvider(BaseIntegrationProvider):
    channel = "instagram"

    def is_configured(self) -> bool:
        return True

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        logger.info(f"[MockInstagram] Sending to {recipient_id}: {content[:50]}")
        return OutgoingResult(success=True, external_message_id=f"mock_ig_msg_{hash(content) & 0xFFFFFF}")

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        if payload.get("hub.mode") == "subscribe" and payload.get("hub.verify_token") == settings.META_VERIFY_TOKEN:
            return payload.get("hub.challenge", "")
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/instagram/callback?mock=true&state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {"instagram_access_token": "mock_ig_token_abc123"}


def get_instagram_provider(integration=None) -> BaseIntegrationProvider:
    if integration and integration.get_credentials().get("instagram_access_token"):
        return InstagramProvider(integration)
    if settings.META_APP_ID and settings.META_APP_SECRET:
        return InstagramProvider(integration)
    return MockInstagramProvider(integration)
