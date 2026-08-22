from rest_framework import serializers
from .models import Workspace, WorkspaceMembership, WorkspaceSettings


class WorkspaceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceSettings
        fields = "__all__"
        read_only_fields = ["workspace", "created_at", "updated_at"]


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "logo", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]


class WorkspaceMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceMembership
        fields = ["id", "workspace", "user", "user_email", "user_name", "role", "permissions", "joined_at"]
        read_only_fields = ["workspace", "user", "joined_at"]

    def get_user_name(self, obj):
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name or obj.user.username

    def get_user(self, obj):
        return {
            "id": str(obj.user.id),
            "email": obj.user.email,
            "first_name": obj.user.first_name,
            "last_name": obj.user.last_name,
            "username": obj.user.username,
        }


class CreateWorkspaceSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=255)
