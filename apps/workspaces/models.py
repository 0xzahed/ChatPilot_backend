import uuid
from django.db import models
from django.conf import settings


class Workspace(models.Model):
    """A tenant/business. All customer-facing data is scoped to a workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    logo = models.ImageField(upload_to="workspace_logos/", blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_workspaces")
    is_active = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspaces"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class WorkspaceMembership(models.Model):
    """Maps a user to a workspace with a role."""

    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("manager", "Manager"),
        ("agent", "Agent"),
        ("viewer", "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="agent")
    permissions = models.JSONField(default=dict, blank=True)
    invited_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workspace_memberships"
        unique_together = ["workspace", "user"]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user.email} — {self.role} @ {self.workspace.name}"

    @property
    def is_admin(self):
        return self.role in ["owner", "admin"]


class WorkspaceSettings(models.Model):
    """Per-workspace configuration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="settings")
    timezone = models.CharField(max_length=50, default="UTC")
    default_language = models.CharField(max_length=10, default="en")
    business_name = models.CharField(max_length=255, blank=True)
    business_description = models.TextField(blank=True)
    working_hours = models.JSONField(default=dict, blank=True)
    delivery_policy = models.TextField(blank=True)
    payment_policy = models.TextField(blank=True)
    return_policy = models.TextField(blank=True)
    refund_policy = models.TextField(blank=True)
    cancellation_policy = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspace_settings"
