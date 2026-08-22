import uuid
from django.db import models
from apps.workspaces.models import Workspace
from apps.customers.models import Customer


class WebchatConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="webchat_config")
    is_enabled = models.BooleanField(default=True)
    title = models.CharField(max_length=100, default="Chat with us")
    welcome_message = models.TextField(default="Hi! How can we help you today?")
    offline_message = models.TextField(default="We're offline. Please leave a message and we'll get back to you.")
    primary_color = models.CharField(max_length=20, default="#6366f1")
    position = models.CharField(max_length=20, default="bottom-right")
    logo_url = models.URLField(blank=True, default="")
    allowed_domains = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webchat_configs"


class WebchatSession(models.Model):
    """A website visitor's chat session. May be linked to a Customer after identification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="webchat_sessions")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="webchat_sessions")
    session_token = models.CharField(max_length=255, unique=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="Anonymous")
    visitor_email = models.EmailField(blank=True, default="")
    visitor_phone = models.CharField(max_length=20, blank=True, default="")
    is_online = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "webchat_sessions"
        ordering = ["-created_at"]
