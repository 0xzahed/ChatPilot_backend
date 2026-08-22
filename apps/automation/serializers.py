from rest_framework import serializers
from .models import AutomationRule, Comment


class AutomationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationRule
        fields = [
            "id", "workspace", "name", "rule_type", "is_active",
            "keywords", "conditions", "response_template", "use_ai",
            "channel", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = "__all__"
        read_only_fields = ["id", "workspace", "external_id", "created_at"]
