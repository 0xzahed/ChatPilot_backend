from rest_framework import serializers
from .models import Integration, WebhookEvent, SyncLog


class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = [
            "id", "workspace", "integration_type", "status", "is_active",
            "display_name", "config", "last_synced_at", "last_error",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "credentials_encrypted", "last_synced_at", "last_error", "created_at", "updated_at"]


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = "__all__"


class SyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncLog
        fields = "__all__"
