from rest_framework import serializers
from .models import Conversation, Message, MessageAttachment, Label, ConversationLabel, TypingIndicator


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name", "color", "created_at"]
        read_only_fields = ["id", "created_at"]


class ConversationListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_avatar = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    labels = LabelSerializer(many=True, read_only=True)
    channel_icon = serializers.CharField(source="channel", read_only=True)
    page_name = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "customer", "customer_name", "customer_avatar", "customer_phone",
            "channel", "channel_icon", "status", "handled_by", "assigned_to",
            "assigned_to_name", "labels", "last_message_at", "last_message_preview",
            "unread_count", "is_complaint", "has_order", "ai_enabled", "language",
            "page_name", "created_at", "updated_at",
        ]

    def get_customer_avatar(self, obj):
        # Check uploaded avatar first
        if obj.customer.avatar:
            return obj.customer.avatar.url
        # Use annotated value from queryset (avoids N+1)
        return getattr(obj, "_channel_avatar", None) or None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            name = f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip()
            return name or obj.assigned_to.username
        return None

    def get_page_name(self, obj):
        """Return the Facebook Page name for this conversation, if available."""
        page_id = (obj.config or {}).get("page_id", "")
        if not page_id:
            return None
        # Use cached page map from serializer context (avoids N+1)
        page_map = self.context.get("_fb_page_map", {})
        if page_map:
            return page_map.get(page_id)
        # Fallback: direct lookup
        from apps.integrations.models import Integration
        integrations = Integration.objects.filter(
            workspace_id=obj.workspace_id,
            integration_type="facebook",
            status="connected",
        )
        for integration in integrations:
            for page in (integration.config or {}).get("connected_pages", []):
                if page.get("page_id") == page_id:
                    return page.get("page_name")
        return None


class ConversationDetailSerializer(ConversationListSerializer):
    customer_detail = serializers.SerializerMethodField()

    def get_customer_detail(self, obj):
        from apps.customers.serializers import CustomerSerializer
        return CustomerSerializer(obj.customer).data

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ["customer_detail", "external_id"]


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = ["id", "file_url", "file_type", "file_name", "file_size", "mime_type", "created_at"]

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None


class MessageSerializer(serializers.ModelSerializer):
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    sender_name = serializers.SerializerMethodField()
    reply_to_content = serializers.CharField(source="reply_to.content", read_only=True, default="")

    class Meta:
        model = Message
        fields = [
            "id", "conversation", "sender_type", "direction", "message_type",
            "content", "status", "attachments", "sender_name", "sent_by",
            "reply_to", "reply_to_content", "ai_metadata", "is_read",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "sender_name", "created_at", "updated_at"]

    def get_sender_name(self, obj):
        if obj.sender_type == "customer":
            return obj.conversation.customer.name
        if obj.sender_type == "ai":
            return "AI Assistant"
        if obj.sent_by:
            name = f"{obj.sent_by.first_name} {obj.sent_by.last_name}".strip()
            return name or obj.sent_by.username
        return "System"


class CreateMessageSerializer(serializers.Serializer):
    content = serializers.CharField(required=True)
    message_type = serializers.CharField(default="text")
    reply_to = serializers.UUIDField(required=False, allow_null=True)
    is_note = serializers.BooleanField(default=False)


class AssignConversationSerializer(serializers.Serializer):
    assigned_to = serializers.UUIDField(required=True)


class UpdateConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["status", "assigned_to", "ai_enabled", "language", "handled_by"]


class TypingIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypingIndicator
        fields = ["id", "conversation", "is_ai", "is_typing", "created_at"]
