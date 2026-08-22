"""Base integration provider interface.

All channel integrations (Facebook, Instagram, WhatsApp, Website, Shopify,
WooCommerce) implement this interface. Mock providers are used when real
credentials are not configured, but the interface is identical.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IncomingMessage:
    """Normalized incoming message from any channel."""
    external_id: str
    channel: str
    sender_external_id: str
    sender_name: str
    content: str
    message_type: str = "text"  # text, image, file, audio
    attachment_url: str = ""
    timestamp: str = ""
    raw_payload: dict = field(default_factory=dict)


@dataclass
class OutgoingResult:
    success: bool
    external_message_id: str = ""
    error: str = ""


class BaseIntegrationProvider(ABC):
    """Abstract base for all integration providers."""

    channel: str = "base"

    def __init__(self, integration=None, **kwargs):
        self.integration = integration
        self.credentials = integration.get_credentials() if integration else {}
        self.config = integration.config if integration else {}

    @abstractmethod
    def send_message(self, recipient_id: str, content: str, message_type: str = "text",
                     attachment_url: str = "") -> OutgoingResult:
        """Send a message to a recipient on this channel."""
        ...

    @abstractmethod
    def process_webhook(self, payload: dict, headers: dict) -> list[IncomingMessage]:
        """Process an incoming webhook and return normalized messages."""
        ...

    @abstractmethod
    def verify_webhook(self, payload: dict, headers: dict) -> str:
        """Verify a webhook challenge from the platform."""
        ...

    @abstractmethod
    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        """Get the OAuth authorization URL (for platforms that support it)."""
        ...

    @abstractmethod
    def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        """Handle the OAuth callback and store credentials."""
        ...

    def is_configured(self) -> bool:
        """Check if the provider has valid credentials."""
        return bool(self.credentials)
