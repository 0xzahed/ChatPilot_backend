"""Platform-wide admin endpoints.

All endpoints require `is_platform_admin=True` on the requesting user.
Provides management of users, workspaces, and platform statistics.
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from django.db.models import Count, Q
from datetime import timedelta

from apps.accounts.models import User
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.inbox.models import Conversation
from apps.orders.models import Order
from apps.customers.models import Customer
from apps.billing.models import Subscription
from apps.audit.models import AuditLog
from common.api_response import api_error, api_success, api_paginated


class IsPlatformAdmin(IsAuthenticated):
    """Permission that also requires `is_platform_admin=True`."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_platform_admin
        )


# ─── Serializers ──────────────────────────────────────────────
class AdminUserSerializer(serializers.ModelSerializer):
    workspace_count = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "username", "first_name", "last_name", "full_name",
            "phone", "is_platform_admin", "is_staff", "is_active",
            "email_verified_at", "last_active_at", "date_joined",
            "workspace_count", "workspace_name",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_workspace_count(self, obj):
        return obj.workspace_memberships.count()

    def get_workspace_name(self, obj):
        membership = obj.workspace_memberships.select_related("workspace").first()
        return membership.workspace.name if membership else None

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name or obj.username


class AdminWorkspaceSerializer(serializers.ModelSerializer):
    owner_email = serializers.CharField(source="owner.email", read_only=True)
    owner_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()
    customer_count = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            "id", "name", "slug", "logo", "owner", "owner_email", "owner_name",
            "is_active", "is_suspended", "member_count", "conversation_count",
            "customer_count", "plan_name", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]

    def get_owner_name(self, obj):
        name = f"{obj.owner.first_name} {obj.owner.last_name}".strip()
        return name or obj.owner.username

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_conversation_count(self, obj):
        return Conversation.objects.filter(workspace=obj).count()

    def get_customer_count(self, obj):
        return Customer.objects.filter(workspace=obj).count()

    def get_plan_name(self, obj):
        sub = Subscription.objects.filter(workspace=obj).first()
        return sub.plan.name if sub and sub.plan else None


class AdminAuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True, default="")
    workspace_name = serializers.CharField(source="workspace.name", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = "__all__"


# ─── Views ─────────────────────────────────────────────────────
class PlatformStatsView(APIView):
    """Platform-wide statistics for the admin dashboard."""
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        platform_admins = User.objects.filter(is_platform_admin=True).count()
        total_workspaces = Workspace.objects.count()
        active_workspaces = Workspace.objects.filter(is_active=True, is_suspended=False).count()
        suspended_workspaces = Workspace.objects.filter(is_suspended=True).count()
        total_conversations = Conversation.objects.count()
        open_conversations = Conversation.objects.filter(status="open").count()
        total_customers = Customer.objects.count()
        total_orders = Order.objects.count()

        # Recent growth (last 7 days)
        from django.utils import timezone
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        new_users_7d = User.objects.filter(date_joined__gte=week_ago).count()
        new_workspaces_7d = Workspace.objects.filter(created_at__gte=week_ago).count()
        new_conversations_7d = Conversation.objects.filter(created_at__gte=week_ago).count()

        # Workspace distribution by plan
        plan_distribution = []
        for sub in Subscription.objects.select_related("plan").all():
            plan_distribution.append({
                "plan": sub.plan.name if sub.plan else "None",
                "workspace_id": str(sub.workspace_id),
                "status": sub.status,
            })

        return api_success(data={
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": total_users - active_users,
                "platform_admins": platform_admins,
                "new_7d": new_users_7d,
            },
            "workspaces": {
                "total": total_workspaces,
                "active": active_workspaces,
                "suspended": suspended_workspaces,
                "new_7d": new_workspaces_7d,
            },
            "conversations": {
                "total": total_conversations,
                "open": open_conversations,
                "new_7d": new_conversations_7d,
            },
            "customers": {
                "total": total_customers,
            },
            "orders": {
                "total": total_orders,
            },
            "plan_distribution": plan_distribution,
        }, message="Dashboard stats")


class AdminUserListView(generics.ListCreateAPIView):
    """List all platform users (with search/filter) or create a new user."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = User.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        qs = User.objects.all().order_by("-date_joined")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        is_admin = self.request.query_params.get("is_platform_admin")
        if is_admin is not None:
            qs = qs.filter(is_platform_admin=is_admin.lower() == "true")
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        return qs


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a specific user."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = User.objects.all()

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        # Toggle platform admin
        if "is_platform_admin" in request.data:
            user.is_platform_admin = request.data["is_platform_admin"]
        if "is_staff" in request.data:
            user.is_staff = request.data["is_staff"]
        if "is_active" in request.data:
            user.is_active = request.data["is_active"]
        if "first_name" in request.data:
            user.first_name = request.data["first_name"]
        if "last_name" in request.data:
            user.last_name = request.data["last_name"]
        if "phone" in request.data:
            user.phone = request.data["phone"]
        user.save()
        return Response(AdminUserSerializer(user).data)


class AdminWorkspaceListView(generics.ListCreateAPIView):
    """List all workspaces (with search/filter)."""
    serializer_class = AdminWorkspaceSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = Workspace.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        qs = Workspace.objects.all().order_by("-created_at").select_related("owner")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(owner__email__icontains=search)
            )
        is_suspended = self.request.query_params.get("is_suspended")
        if is_suspended is not None:
            qs = qs.filter(is_suspended=is_suspended.lower() == "true")
        return qs


class AdminWorkspaceDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a specific workspace."""
    serializer_class = AdminWorkspaceSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = Workspace.objects.all()

    def patch(self, request, *args, **kwargs):
        ws = self.get_object()
        if "is_active" in request.data:
            ws.is_active = request.data["is_active"]
        if "is_suspended" in request.data:
            ws.is_suspended = request.data["is_suspended"]
        if "name" in request.data:
            ws.name = request.data["name"]
        if "slug" in request.data:
            ws.slug = request.data["slug"]
        ws.save()
        return Response(AdminWorkspaceSerializer(ws).data)


class AdminAuditLogListView(generics.ListAPIView):
    queryset = AuditLog.objects.none()
    """List all audit logs across the platform."""
    serializer_class = AdminAuditLogSerializer
    permission_classes = [IsPlatformAdmin]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        qs = AuditLog.objects.all().select_related("user", "workspace").order_by("-created_at")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(action__icontains=search)
                | Q(user__email__icontains=search)
                | Q(workspace__name__icontains=search)
                | Q(description__icontains=search)
            )
        action = self.request.query_params.get("action")
        if action:
            qs = qs.filter(action__iexact=action)
        workspace_id = self.request.query_params.get("workspace_id")
        if workspace_id:
            qs = qs.filter(workspace_id=workspace_id)
        return qs
