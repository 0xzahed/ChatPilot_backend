from rest_framework import generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Notification
from apps.inbox.views import get_user_workspaces


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
        notif = Notification.objects.filter(id=pk).first()
        if not notif:
            return Response({"error": "Not found."}, status=404)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response({"detail": "Marked as read."})


class MarkAllNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ws_ids = get_user_workspaces(request.user)
        Notification.objects.filter(workspace_id__in=ws_ids, is_read=False).update(is_read=True)
        return Response({"detail": "All marked as read."})
