import uuid
from django.db import models
from django.conf import settings
from apps.workspaces.models import Workspace


class Label(models.Model):
    """Custom labels for conversations and customers."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="labels")
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default="blue")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labels"
        unique_together = ["workspace", "name"]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Conversation(models.Model):
    """A conversation between a customer and the business on a given channel."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("pending", "Pending"),
    ]

    CHANNEL_CHOICES = [
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("whatsapp", "WhatsApp"),
        ("website", "Website"),
    ]

    HANDLED_BY_CHOICES = [
        ("ai", "AI"),
        ("human", "Human"),
        ("mixed", "Mixed"),
        ("unassigned", "Unassigned"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="conversations")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="website")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    handled_by = models.CharField(max_length=20, choices=HANDLED_BY_CHOICES, default="unassigned")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_conversations",
    )
    labels = models.ManyToManyField(Label, through="ConversationLabel", related_name="conversations")
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.TextField(blank=True, default="")
    unread_count = models.PositiveIntegerField(default=0)
    is_complaint = models.BooleanField(default=False)
    has_order = models.BooleanField(default=False)
    ai_enabled = models.BooleanField(default=True)
    language = models.CharField(max_length=10, default="en")
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversations"
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "channel"]),
            models.Index(fields=["workspace", "assigned_to"]),
            models.Index(fields=["workspace", "handled_by"]),
            models.Index(fields=["workspace", "is_complaint"]),
        ]

    def __str__(self):
        return f"{self.customer.name} — {self.channel}"


class ConversationLabel(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    label = models.ForeignKey(Label, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_labels"
        unique_together = ["conversation", "label"]


class Message(models.Model):
    """A single message in a conversation."""

    SENDER_CHOICES = [
        ("customer", "Customer"),
        ("agent", "Agent"),
        ("ai", "AI"),
        ("system", "System"),
    ]

    DIRECTION_CHOICES = [
        ("inbound", "Inbound"),
        ("outbound", "Outbound"),
    ]

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("read", "Read"),
        ("failed", "Failed"),
    ]

    TYPE_CHOICES = [
        ("text", "Text"),
        ("image", "Image"),
        ("file", "File"),
        ("audio", "Audio"),
        ("video", "Video"),
        ("system", "System"),
        ("note", "Internal Note"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="messages")
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES, default="customer")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default="inbound")
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="text")
    content = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="sent")
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sent_messages",
    )
    ai_metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["workspace", "sender_type"]),
        ]

    def __str__(self):
        return f"{self.sender_type}: {self.content[:50]}"


class MessageAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/")
    file_type = models.CharField(max_length=50, default="image")
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    thumbnail = models.ImageField(upload_to="attachments/thumbs/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "message_attachments"


class TypingIndicator(models.Model):
    """Tracks who is currently typing in a conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="typing_indicators")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    is_ai = models.BooleanField(default=False)
    is_typing = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "typing_indicators"
