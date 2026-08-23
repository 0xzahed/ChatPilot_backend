from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Complaint
from .serializers import ComplaintSerializer
from apps.inbox.views import get_user_workspaces


class ComplaintListView(generics.ListCreateAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = Complaint.objects.filter(workspace_id__in=ws_ids).select_related("customer", "assigned_to")

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)

        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(customer__name__icontains=search)
            )

        return qs

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class ComplaintDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Complaint.objects.filter(workspace_id__in=ws_ids)
