from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from common.permissions import WorkspaceRolePermission, resolve_create_workspace_id
from django.db.models import Q
from .models import Complaint
from .serializers import ComplaintSerializer
from apps.inbox.views import get_user_workspaces
from apps.complaints.models import Complaint


class ComplaintListView(generics.ListCreateAPIView):
    queryset = Complaint.objects.none()
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
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
        serializer.save(workspace_id=resolve_create_workspace_id(self.request))


class ComplaintDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Complaint.objects.filter(workspace_id__in=ws_ids)
