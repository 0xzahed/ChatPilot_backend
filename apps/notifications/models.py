import uuid
from django.db import models
from django.conf import settings
from apps.workspaces.models import Workspace


class Notification(models.Model):
    TYPE_CHOICES = [
        ("new_message", "New Message"),
        ("conversation_assigned", "Conversation Assigned"),
        ("complaint", "Complaint"),
        ("order", "Order"),
        ("integration_failed", "Integration Failed"),
        ("ai_escalation", "AI Escalation"),
        ("system", "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "user", "is_read"])]
