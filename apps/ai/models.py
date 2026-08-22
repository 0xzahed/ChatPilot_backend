import uuid
from django.db import models
from apps.workspaces.models import Workspace
from apps.inbox.models import Conversation, Message


class AISettings(models.Model):
    MODE_CHOICES = [
        ("off", "Off"),
        ("suggest_only", "Suggest Only"),
        ("auto_reply", "Auto Reply"),
        ("hybrid", "Hybrid"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="ai_settings")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="suggest_only")
    provider = models.CharField(max_length=50, default="mock")
    model_name = models.CharField(max_length=100, default="gpt-4o-mini")
    api_key_encrypted = models.TextField(blank=True, default="")
    base_url = models.URLField(blank=True, default="")
    temperature = models.FloatField(default=0.7)
    max_tokens = models.PositiveIntegerField(default=2048)
    enable_vision = models.BooleanField(default=True)
    enable_complaint_detection = models.BooleanField(default=True)
    enable_language_detection = models.BooleanField(default=True)
    enable_human_handoff = models.BooleanField(default=True)
    confidence_threshold = models.FloatField(default=0.7)
    safety_rules = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_settings"


class AIInstructions(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="ai_instructions")
    business_name = models.CharField(max_length=255, blank=True, default="")
    business_description = models.TextField(blank=True, default="")
    tone = models.CharField(max_length=100, default="polite, professional")
    language = models.CharField(max_length=10, default="en")
    greeting = models.TextField(blank=True, default="")
    working_hours = models.JSONField(default=dict, blank=True)
    delivery_policy = models.TextField(blank=True, default="")
    payment_policy = models.TextField(blank=True, default="")
    return_policy = models.TextField(blank=True, default="")
    refund_policy = models.TextField(blank=True, default="")
    cancellation_policy = models.TextField(blank=True, default="")
    escalation_rules = models.JSONField(default=list, blank=True)
    prohibited_responses = models.JSONField(default=list, blank=True)
    sales_strategy = models.TextField(blank=True, default="")
    faqs = models.JSONField(default=list, blank=True)
    custom_instructions = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_instructions"


class AIEvent(models.Model):
    """Log of every AI action for audit and analytics."""

    EVENT_TYPE_CHOICES = [
        ("suggestion", "Suggestion"),
        ("auto_reply", "Auto Reply"),
        ("language_detection", "Language Detection"),
        ("complaint_detection", "Complaint Detection"),
        ("intent_detection", "Intent Detection"),
        ("product_recognition", "Product Recognition"),
        ("handoff", "Human Handoff"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_events")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_events")
    message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_events")
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    input_text = models.TextField(blank=True, default="")
    output_text = models.TextField(blank=True, default="")
    detected_language = models.CharField(max_length=10, blank=True, default="")
    detected_intent = models.CharField(max_length=100, blank=True, default="")
    is_complaint = models.BooleanField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    model_name = models.CharField(max_length=100, blank=True, default="")
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_events"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "event_type"])]


class AIUsage(models.Model):
    """Aggregated AI usage per workspace per day for quota tracking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_usage_records")
    date = models.DateField()
    ai_replies = models.PositiveIntegerField(default=0)
    ai_suggestions = models.PositiveIntegerField(default=0)
    comment_automation = models.PositiveIntegerField(default=0)
    vision_requests = models.PositiveIntegerField(default=0)
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)

    class Meta:
        db_table = "ai_usage"
        unique_together = ["workspace", "date"]
        ordering = ["-date"]
