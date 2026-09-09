from rest_framework import generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Notification
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated


class NotificationSer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = Notification.objects.filter(
            Q(workspace_id__in=ws_ids) | Q(user=self.request.user)
        ).order_by("-created_at")
        is_read = self.request.query_params.get("is_read")
        if is_read == "false":
            qs = qs.filter(is_read=False)
        return qs


class MarkNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ws_ids = get_user_workspaces(request.user)
        notif = Notification.objects.filter(
            Q(id=pk, workspace_id__in=ws_ids) | Q(id=pk, user=request.user)
        ).first()
        if not notif:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return api_success(message="Marked as read")


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ws_ids = get_user_workspaces(request.user)
        Notification.objects.filter(workspace_id__in=ws_ids, is_read=False).update(is_read=True)
        return api_success(message="All marked as read")
