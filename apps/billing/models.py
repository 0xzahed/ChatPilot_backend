import uuid
from django.db import models
from apps.workspaces.models import Workspace
from django.conf import settings


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="BDT")
    message_limit = models.PositiveIntegerField(default=6600)
    team_member_limit = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=False)
    features = models.JSONField(default=list, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "plans"
        ordering = ["sort_order", "price_monthly"]


class Subscription(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("trialing", "Trialing"),
        ("past_due", "Past Due"),
        ("canceled", "Canceled"),
        ("expired", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    billing_cycle = models.CharField(max_length=20, default="monthly")  # monthly, yearly
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    provider = models.CharField(max_length=50, blank=True, default="")  # stripe, sslcommerz, etc.
    provider_subscription_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"


class Invoice(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("paid", "Paid"),
        ("open", "Open"),
        ("void", "Void"),
        ("uncollectible", "Uncollectible"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invoices")
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="BDT")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    due_date = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    provider_invoice_id = models.CharField(max_length=255, blank=True, default="")
    line_items = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]


class UsageRecord(models.Model):
    """Monthly usage record for quota tracking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="usage_records")
    period_start = models.DateField()
    period_end = models.DateField()
    messages_used = models.PositiveIntegerField(default=0)
    ai_replies = models.PositiveIntegerField(default=0)
    ai_suggestions = models.PositiveIntegerField(default=0)
    comment_automation = models.PositiveIntegerField(default=0)
    vision_requests = models.PositiveIntegerField(default=0)
    tokens_used = models.PositiveIntegerField(default=0)
    storage_used_mb = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "usage_records"
        unique_together = ["workspace", "period_start"]
        ordering = ["-period_start"]
