from rest_framework import serializers
from .models import WebchatConfig, WebchatSession


class WebchatConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebchatConfig
        fields = "__all__"
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]


class WebchatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebchatSession
        fields = "__all__"
