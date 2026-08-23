from rest_framework import serializers
from .models import AISettings, AIInstructions, AIEvent, AIUsage


class AISettingsSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = AISettings
        fields = [
            "id", "workspace", "mode", "provider", "model_name", "base_url",
            "api_key", "temperature", "max_tokens", "enable_vision", "enable_complaint_detection",
            "enable_language_detection", "enable_human_handoff", "confidence_threshold",
            "safety_rules", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        api_key = validated_data.pop("api_key", None)
        if api_key:
            from common.utils import encrypt_value
            instance.api_key_encrypted = encrypt_value(api_key)
        return super().update(instance, validated_data)


class AIInstructionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIInstructions
        fields = "__all__"
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]


class AIEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIEvent
        fields = "__all__"


class AIUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIUsage
        fields = "__all__"
