import uuid
from django.db import models
from django.conf import settings
from apps.workspaces.models import Workspace


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action = models.CharField(max_length=100)  # create, update, delete, login, etc.
    resource_type = models.CharField(max_length=50)  # conversation, product, order, etc.
    resource_id = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "resource_type"])]
