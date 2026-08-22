import uuid
from django.db import models
from apps.workspaces.models import Workspace
from apps.inbox.models import Conversation


class AutomationRule(models.Model):
    RULE_TYPE_CHOICES = [
        ("keyword", "Keyword"),
        ("ai", "AI"),
        ("comment", "Comment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="automation_rules")
    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES, default="keyword")
    is_active = models.BooleanField(default=True)
    keywords = models.JSONField(default=list, blank=True)  # ["price", "দাম", "how much"]
    conditions = models.JSONField(default=dict, blank=True)
    response_template = models.TextField(blank=True, default="")
    use_ai = models.BooleanField(default=False)
    channel = models.CharField(max_length=20, blank=True, default="")  # empty = all channels
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "automation_rules"
        ordering = ["-created_at"]


class Comment(models.Model):
    """Social media comment synced from Facebook/Instagram."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="comments")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="comments")
    external_id = models.CharField(max_length=255, unique=True)
    channel = models.CharField(max_length=20)  # facebook, instagram
    post_id = models.CharField(max_length=255, blank=True, default="")
    author_name = models.CharField(max_length=255, blank=True, default="")
    author_external_id = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField(blank=True, default="")
    reply = models.TextField(blank=True, default="")
    is_replied = models.BooleanField(default=False)
    is_auto_replied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "comments"
        ordering = ["-created_at"]
