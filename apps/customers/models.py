import uuid
from django.db import models
from django.conf import settings
from apps.workspaces.models import Workspace
from apps.inbox.models import Label


class Customer(models.Model):
    """A customer scoped to a workspace. Can have multiple channel identities."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=255, blank=True, default="Unknown")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    avatar = models.ImageField(upload_to="customer_avatars/", blank=True, null=True)
    labels = models.ManyToManyField(Label, blank=True, related_name="customers")
    tags = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_customers",
    )
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    last_interaction_at = models.DateTimeField(null=True, blank=True)
    is_vip = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default="en")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customers"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "name"]),
            models.Index(fields=["workspace", "phone"]),
            models.Index(fields=["workspace", "email"]),
        ]

    def __str__(self):
        return self.name or self.phone or str(self.id)


class CustomerChannel(models.Model):
    """A customer's identity on a specific channel (FB PSID, IG ID, WA number, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="channels")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="customer_channels")
    channel = models.CharField(max_length=20)  # facebook, instagram, whatsapp, website
    external_id = models.CharField(max_length=255)  # PSID, IG ID, phone number, visitor ID
    display_name = models.CharField(max_length=255, blank=True)
    profile_url = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_channels"
        unique_together = ["workspace", "channel", "external_id"]
        indexes = [models.Index(fields=["workspace", "channel", "external_id"])]


class CustomerTimelineEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="timeline")
    event_type = models.CharField(max_length=50)  # conversation_started, order_created, etc.
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "customer_timeline_events"
        ordering = ["-created_at"]
