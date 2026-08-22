from rest_framework import serializers
from .models import AISettings, AIInstructions, AIEvent, AIUsage


class AISettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AISettings
        fields = [
            "id", "workspace", "mode", "provider", "model_name", "base_url",
            "temperature", "max_tokens", "enable_vision", "enable_complaint_detection",
            "enable_language_detection", "enable_human_handoff", "confidence_threshold",
            "safety_rules", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]
        extra_kwargs = {"api_key_encrypted": {"write_only": True}}


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
