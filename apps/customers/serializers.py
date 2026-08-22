from rest_framework import serializers
from .models import Customer, CustomerChannel, CustomerTimelineEvent


class LabelMiniSerializer(serializers.Serializer):
    """Inline label serializer to avoid circular imports."""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)


class CustomerChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerChannel
        fields = ["id", "channel", "external_id", "display_name", "profile_url", "created_at"]
        read_only_fields = ["id", "created_at"]


class CustomerSerializer(serializers.ModelSerializer):
    channels = CustomerChannelSerializer(many=True, read_only=True)
    labels = LabelMiniSerializer(many=True, read_only=True)
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "name", "email", "phone", "avatar", "labels", "tags", "notes",
            "assigned_to", "assigned_to_name", "total_spent", "total_orders",
            "last_interaction_at", "is_vip", "language", "channels", "metadata",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "total_spent", "total_orders", "last_interaction_at", "created_at", "updated_at"]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            name = f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip()
            return name or obj.assigned_to.username
        return None


class CustomerListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list view."""

    assigned_to_name = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id", "name", "email", "phone", "avatar", "assigned_to_name",
            "total_spent", "total_orders", "is_vip", "language",
            "last_interaction_at", "conversation_count", "created_at",
        ]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            name = f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip()
            return name or obj.assigned_to.username
        return None

    def get_conversation_count(self, obj):
        return obj.conversations.count()


class CustomerTimelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerTimelineEvent
        fields = ["id", "event_type", "description", "metadata", "created_at"]
