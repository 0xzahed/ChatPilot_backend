from rest_framework import serializers
from .models import Complaint


class ComplaintSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    conversation_id = serializers.UUIDField(source="conversation.id", read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "workspace", "customer", "customer_name", "customer_phone",
            "conversation", "conversation_id", "title", "description",
            "status", "priority", "assigned_to", "assigned_to_name",
            "detected_by_ai", "resolution_notes", "resolved_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "detected_by_ai", "resolved_at", "created_at", "updated_at"]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            name = f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip()
            return name or obj.assigned_to.username
        return None
