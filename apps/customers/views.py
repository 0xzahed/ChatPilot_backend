from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from common.permissions import WorkspaceRolePermission, resolve_create_workspace_id
from django.db.models import Q, Count
from .models import Customer, CustomerTimelineEvent
from .serializers import CustomerSerializer, CustomerListSerializer, CustomerTimelineSerializer
from apps.inbox.views import get_user_workspaces
from apps.customers.models import Customer
from apps.customers.models import CustomerTimelineEvent


class CustomerListView(generics.ListCreateAPIView):
    queryset = Customer.objects.none()
    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CustomerListSerializer
        return CustomerSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        qs = Customer.objects.filter(workspace_id__in=ws_ids).annotate(
            conversation_count=Count("conversations"),
        ).select_related("assigned_to").order_by("-created_at")

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))

        is_vip = self.request.query_params.get("is_vip")
        if is_vip == "true":
            qs = qs.filter(is_vip=True)

        return qs

    def perform_create(self, serializer):
        serializer.save(workspace_id=resolve_create_workspace_id(self.request))


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Customer.objects.filter(workspace_id__in=ws_ids)


class CustomerTimelineView(generics.ListAPIView):
    queryset = CustomerTimelineEvent.objects.none()
    serializer_class = CustomerTimelineSerializer
    permission_classes = [IsAuthenticated, WorkspaceRolePermission]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return CustomerTimelineEvent.objects.filter(
            customer_id=self.kwargs["pk"],
            customer__workspace_id__in=ws_ids,
        )
