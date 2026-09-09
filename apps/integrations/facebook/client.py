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
        return bool(self.credentials.get("pages")) or bool(self.credentials.get("page_access_token"))

    def _get_page_token(self, page_id: str = "") -> str:
        """Look up the access token for a specific page from stored credentials."""
        pages = self.credentials.get("pages", [])
        if page_id:
            for p in pages:
                if p.get("page_id") == page_id:
                    return p.get("page_access_token", "")
        # Fallback: single-page legacy format
        if pages:
            return pages[0].get("page_access_token", "")
        return self.credentials.get("page_access_token", "")

    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "", page_id: str = "") -> OutgoingResult:
        token = self._get_page_token(page_id)
        if not token:
            raise IntegrationNotConfiguredError("Facebook page access token not configured.")

        url = f"{GRAPH_API_BASE}/me/messages"
        params = {"access_token": token}

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
                        external_id=message.get("mid", messaging_event.get("message_id", "")),
                        channel="facebook",
                        sender_external_id=sender_id,
                        sender_name="",  # Will be fetched via API
                        content=content,
                        message_type=msg_type,
                        attachment_url=attachment_url,
                        timestamp=messaging_event.get("timestamp", ""),
                        page_id=recipient_id,
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
            f"&scope=pages_messaging,pages_read_engagement,pages_show_list,pages_manage_metadata"
        )

    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        """Exchange OAuth code for user access token, then fetch ALL available pages.

        Returns a dict with user_access_token and a list of available pages
        (each with id, name, access_token). The caller is responsible for
        letting the user select which pages to connect.
        """
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

                pages = []

                # Get pages — try /me/accounts first (Classic Pages)
                pages_url = f"{GRAPH_API_BASE}/me/accounts"
                pages_resp = client.get(pages_url, params={
                    "access_token": user_token,
                    "fields": "id,name,access_token,tasks",
                    "limit": 100,
                })
                pages_resp.raise_for_status()
                pages_data = pages_resp.json()

                for page in pages_data.get("data", []):
                    pages.append({
                        "page_id": page["id"],
                        "page_name": page.get("name", ""),
                        "page_access_token": page.get("access_token", ""),
                    })

                # New Pages Experience: /me/accounts may return empty,
                # but granular_scopes in debug_token has target_ids (page IDs).
                if not pages:
                    try:
                        debug_resp = client.get(
                            f"{GRAPH_API_BASE}/debug_token",
                            params={"input_token": user_token, "access_token": user_token},
                        )
                        debug_data = debug_resp.json().get("data", {})
                        granular = debug_data.get("granular_scopes", [])
                        page_ids = set()
                        for gs in granular:
                            for tid in gs.get("target_ids", []):
                                page_ids.add(tid)

                        for pid in page_ids:
                            page_resp = client.get(
                                f"{GRAPH_API_BASE}/{pid}",
                                params={
                                    "access_token": user_token,
                                    "fields": "id,name,access_token",
                                },
                            )
                            if page_resp.status_code == 200:
                                pdata = page_resp.json()
                                if pdata.get("access_token"):
                                    pages.append({
                                        "page_id": pdata["id"],
                                        "page_name": pdata.get("name", ""),
                                        "page_access_token": pdata["access_token"],
                                    })
                    except Exception as e:
                        logger.warning(f"Facebook OAuth: granular scope page lookup failed: {e}")

                logger.info(f"Facebook OAuth: found {len(pages)} pages")
                return {
                    "user_access_token": user_token,
                    "available_pages": pages,
                }
        except Exception as e:
            logger.error(f"Facebook OAuth error: {e}")
            raise

    def fetch_historical_conversations(self) -> list[dict]:
        """Fetch past Messenger conversations from all connected Facebook Pages.

        Uses the Page conversations API to retrieve threads and messages.
        Returns a list of dicts: [{thread_id, sender_id, sender_name, page_id, messages: [{...}]}]
        """
        pages = self.credentials.get("pages", [])
        # Legacy single-page fallback
        if not pages and self.credentials.get("page_access_token"):
            pages = [{
                "page_id": self.credentials.get("page_id", ""),
                "page_access_token": self.credentials.get("page_access_token", ""),
            }]

        if not pages:
            logger.warning("Facebook: no pages configured for historical sync")
            return []

        results = []

        try:
            with httpx.Client(timeout=60) as client:
                for page in pages:
                    token = page.get("page_access_token", "")
                    page_id = page.get("page_id", "")
                    if not token or not page_id:
                        continue

                    endpoint = f"{GRAPH_API_BASE}/{page_id}/conversations"
                    resp = client.get(endpoint, params={
                        "access_token": token,
                        "fields": "id,link,message_count,snippet,updated_time,participants,messages{message,from,created_time,id}",
                        "limit": 50,
                    })
                    resp.raise_for_status()
                    data = resp.json()

                    for thread in data.get("data", []):
                        thread_id = thread.get("id", "")
                        participants = thread.get("participants", {}).get("data", [])
                        sender = next((p for p in participants if p.get("id") != page_id), participants[0] if participants else {})
                        sender_id = sender.get("id", "")
                        sender_name = sender.get("name", "Unknown")

                        # Fetch sender profile picture
                        sender_pic = ""
                        try:
                            pic_resp = client.get(
                                f"{GRAPH_API_BASE}/{sender_id}/picture",
                                params={"access_token": token, "redirect": "false", "height": 200, "width": 200},
                            )
                            pic_resp.raise_for_status()
                            pic_data = pic_resp.json()
                            sender_pic = pic_data.get("data", {}).get("url", "")
                        except Exception:
                            pass

                        messages = []
                        msg_data = thread.get("messages", {}).get("data", [])
                        for m in msg_data:
                            messages.append({
                                "id": m.get("id", ""),
                                "content": m.get("message", ""),
                                "created_time": m.get("created_time", ""),
                                "from_id": m.get("from", {}).get("id", ""),
                                "from_name": m.get("from", {}).get("name", ""),
                            })

                        results.append({
                            "thread_id": thread_id,
                            "page_id": page_id,
                            "sender_id": sender_id,
                            "sender_name": sender_name,
                            "sender_pic": sender_pic,
                            "snippet": thread.get("snippet", ""),
                            "updated_time": thread.get("updated_time", ""),
                            "message_count": thread.get("message_count", 0),
                            "messages": messages,
                        })

                    logger.info(f"Facebook: fetched {len(results)} historical conversations from page {page_id}")

            return results

        except Exception as e:
            logger.error(f"Facebook historical sync error: {e}")
            return []


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
            "user_access_token": "mock_user_token_abc123",
            "available_pages": [
                {"page_id": "mock_page_123", "page_name": "Demo Business Page", "page_access_token": "mock_page_token_abc123"},
                {"page_id": "mock_page_456", "page_name": "Demo Store Page", "page_access_token": "mock_page_token_def456"},
            ],
        }


def get_facebook_provider(integration=None) -> BaseIntegrationProvider:
    """Return real or mock provider based on configuration."""
    if integration:
        creds = integration.get_credentials()
        # Multi-page format
        if creds.get("pages"):
            return FacebookProvider(integration)
        # Legacy single-page format
        if creds.get("page_access_token"):
            return FacebookProvider(integration)
    if settings.META_APP_ID and settings.META_APP_SECRET:
        return FacebookProvider(integration)
    return MockFacebookProvider(integration)
