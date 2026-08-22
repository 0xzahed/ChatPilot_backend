from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta
from .models import Plan, Subscription, Invoice, UsageRecord
from .serializers import PlanSerializer, SubscriptionSerializer, InvoiceSerializer, UsageRecordSerializer
from apps.inbox.views import get_user_workspaces


class PlanListView(generics.ListAPIView):
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]
    queryset = Plan.objects.filter(is_active=True)


class SubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if workspace_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        sub = Subscription.objects.filter(workspace_id=workspace_id).first()
        if not sub:
            return Response({"detail": "No subscription found."})
        return Response(SubscriptionSerializer(sub).data)

    def post(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if workspace_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        plan_id = request.data.get("plan_id")
        plan = Plan.objects.filter(id=plan_id, is_active=True).first()
        if not plan:
            return Response({"error": "Plan not found."}, status=404)
        sub, created = Subscription.objects.update_or_create(
            workspace_id=workspace_id,
            defaults={
                "plan": plan,
                "status": "active",
                "current_period_start": timezone.now(),
                "current_period_end": timezone.now() + timedelta(days=30),
                "billing_cycle": request.data.get("billing_cycle", "monthly"),
            },
        )
        return Response(SubscriptionSerializer(sub).data, status=201 if created else 200)


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Invoice.objects.filter(workspace_id__in=ws_ids)


class UsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if workspace_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        records = UsageRecord.objects.filter(workspace_id=workspace_id).order_by("-period_start")[:12]
        return Response(UsageRecordSerializer(records, many=True).data)
