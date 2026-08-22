from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from .models import AuditLog
from apps.inbox.views import get_user_workspaces


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = "__all__"


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return AuditLog.objects.filter(workspace_id__in=ws_ids).select_related("user")
