"""WhatsApp Business Cloud API integration.

Uses the official WhatsApp Cloud API (Meta-hosted) for sending and
receiving messages. Falls back to mock when credentials are not set.
"""

import httpx
import logging
import json
from django.conf import settings
from ..base.provider import BaseIntegrationProvider, IncomingMessage, OutgoingResult
from ..base.exceptions import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)
WHATSAPP_API_BASE = "https://graph.facebook.com"


class WhatsAppProvider(BaseIntegrationProvider):
    channel = "whatsapp"

    def is_configured(self) -> bool:
        return bool(self.credentials.get("access_token") and self.credentials.get("phone_number_id"))

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("WhatsApp credentials not configured.")

        api_version = settings.WHATSAPP_API_VERSION
        phone_number_id = self.credentials["phone_number_id"]
        url = f"{WHATSAPP_API_BASE}/{api_version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.credentials['access_token']}",
            "Content-Type": "application/json",
        }

        if message_type == "text":
            payload = {"messaging_product": "whatsapp", "to": recipient_id, "type": "text",
                       "text": {"body": content}}
        elif message_type in ("image", "document", "audio", "video"):
            payload = {"messaging_product": "whatsapp", "to": recipient_id, "type": message_type,
                       message_type: {"link": attachment_url}}
        else:
            payload = {"messaging_product": "whatsapp", "to": recipient_id, "type": "text",
                       "text": {"body": content}}

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return OutgoingResult(success=True,
                                      external_message_id=data.get("messages", [{}])[0].get("id", ""))
        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            return OutgoingResult(success=False, error=str(e))

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        messages = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("messaging_product") != "whatsapp":
                    continue
                for msg in value.get("messages", []):
                    msg_type = msg.get("type", "text")
                    content = ""
                    attachment_url = ""
                    if msg_type == "text":
                        content = msg.get("text", {}).get("body", "")
                    elif msg_type in ("image", "document", "audio", "video"):
                        content = msg.get(msg_type, {}).get("caption", "")
                        attachment_url = msg.get(msg_type, {}).get("link", "") or \
                            msg.get(msg_type, {}).get("id", "")

                    messages.append(IncomingMessage(
                        external_id=msg.get("id", ""),
                        channel="whatsapp",
                        sender_external_id=msg.get("from", ""),
                        sender_name=value.get("contacts", [{}])[0].get("profile", {}).get("name", ""),
                        content=content,
                        message_type=msg_type,
                        attachment_url=attachment_url,
                        timestamp=msg.get("timestamp", ""),
                        raw_payload=msg,
                    ))
        return messages

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        mode = payload.get("hub.mode")
        token = payload.get("hub.verify_token")
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            return payload.get("hub.challenge", "")
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        # WhatsApp uses Meta OAuth
        return (
            f"https://www.facebook.com/v20.0/dialog/oauth"
            f"?client_id={settings.META_APP_ID}"
            f"&redirect_uri={redirect_uri}&state={state}"
        )

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "", "phone_number_id": ""}


class MockWhatsAppProvider(BaseIntegrationProvider):
    channel = "whatsapp"

    def is_configured(self) -> bool:
        return True

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        logger.info(f"[MockWhatsApp] Sending to {recipient_id}: {content[:50]}")
        return OutgoingResult(success=True, external_message_id=f"mock_wa_msg_{hash(content) & 0xFFFFFF}")

    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        return []

    def verify_webhook(self, payload: dict, headers: dict) -> str:
        if payload.get("hub.mode") == "subscribe" and payload.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN:
            return payload.get("hub.challenge", "")
        return ""

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return f"{settings.FRONTEND_URL}/integrations/whatsapp/callback?mock=true&state={state}"

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        return {"access_token": "mock_wa_token", "phone_number_id": "mock_phone_id"}


def get_whatsapp_provider(integration=None) -> BaseIntegrationProvider:
    if integration and integration.get_credentials().get("access_token"):
        return WhatsAppProvider(integration)
    if settings.WHATSAPP_ACCESS_TOKEN:
        return WhatsAppProvider(integration)
    return MockWhatsAppProvider(integration)
