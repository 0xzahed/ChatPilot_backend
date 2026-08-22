class IntegrationError(Exception):
    """Base exception for integration errors."""
    pass


class IntegrationNotConfiguredError(IntegrationError):
    """Raised when an integration is not properly configured."""
    pass


class WebhookVerificationError(IntegrationError):
    """Raised when webhook verification fails."""
    pass
