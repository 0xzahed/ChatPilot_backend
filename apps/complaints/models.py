import uuid
from django.db import models
from apps.workspaces.models import Workspace
from apps.customers.models import Customer
from apps.inbox.models import Conversation
from django.conf import settings


class Complaint(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="complaints")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="complaints")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="high")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_complaints")
    detected_by_ai = models.BooleanField(default=True)
    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "complaints"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "priority"]),
        ]
