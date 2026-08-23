from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Customer, CustomerTimelineEvent
from .serializers import CustomerSerializer, CustomerListSerializer, CustomerTimelineSerializer
from apps.inbox.views import get_user_workspaces


class CustomerListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return CustomerListSerializer
        return CustomerSerializer

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = Customer.objects.filter(workspace_id__in=ws_ids)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))

        is_vip = self.request.query_params.get("is_vip")
        if is_vip == "true":
            qs = qs.filter(is_vip=True)

        return qs

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Customer.objects.filter(workspace_id__in=ws_ids)


class CustomerTimelineView(generics.ListAPIView):
    serializer_class = CustomerTimelineSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CustomerTimelineEvent.objects.filter(customer_id=self.kwargs["pk"])
