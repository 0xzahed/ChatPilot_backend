import uuid
from django.db import models
from apps.workspaces.models import Workspace
from common.utils import encrypt_value, decrypt_value


class Integration(models.Model):
    """A connected integration for a workspace (Facebook, WhatsApp, Shopify, etc.)."""

    TYPE_CHOICES = [
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("whatsapp", "WhatsApp"),
        ("website", "Website"),
        ("shopify", "Shopify"),
        ("woocommerce", "WooCommerce"),
    ]

    STATUS_CHOICES = [
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
        ("error", "Error"),
        ("pending", "Pending"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="integrations")
    integration_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    is_active = models.BooleanField(default=True)
    display_name = models.CharField(max_length=255, blank=True, default="")
    config = models.JSONField(default=dict, blank=True)
    # Encrypted credentials — never exposed to frontend
    credentials_encrypted = models.TextField(blank=True, default="")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integrations"
        unique_together = ["workspace", "integration_type"]
        ordering = ["-created_at"]

    def set_credentials(self, credentials: dict):
        import json
        encrypted = {}
        for key, value in credentials.items():
            encrypted[key] = encrypt_value(str(value)) if value else ""
        self.credentials_encrypted = json.dumps(encrypted)

    def get_credentials(self) -> dict:
        import json
        if not self.credentials_encrypted:
            return {}
        try:
            encrypted = json.loads(self.credentials_encrypted)
            return {k: decrypt_value(v) for k, v in encrypted.items()}
        except Exception:
            return {}


class WebhookEvent(models.Model):
    """Incoming webhook events from external platforms."""

    STATUS_CHOICES = [
        ("received", "Received"),
        ("processing", "Processing"),
        ("processed", "Processed"),
        ("failed", "Failed"),
        ("dead_letter", "Dead Letter"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="webhook_events", null=True, blank=True)
    source = models.CharField(max_length=50)  # facebook, instagram, whatsapp, shopify
    event_type = models.CharField(max_length=100, blank=True, default="")
    external_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    payload = models.JSONField(default=dict)
    signature = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="received")
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "webhook_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["external_id"]),
        ]


class SyncLog(models.Model):
    """Log for Shopify/WooCommerce product/order sync operations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="sync_logs")
    sync_type = models.CharField(max_length=50)  # initial, incremental, webhook, manual
    entity_type = models.CharField(max_length=50)  # products, orders, customers
    records_synced = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="success")  # success, failed, partial
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sync_logs"
        ordering = ["-created_at"]
