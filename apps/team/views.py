from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.workspaces.models import WorkspaceMembership, Workspace
from apps.workspaces.serializers import WorkspaceMembershipSerializer
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated
from common.permissions import require_workspace_admin


class TeamListView(generics.ListAPIView):
    queryset = WorkspaceMembership.objects.none()
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return WorkspaceMembership.objects.filter(workspace_id__in=ws_ids).select_related("user", "workspace")


class TeamMemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return WorkspaceMembership.objects.filter(workspace_id__in=ws_ids)

    def patch(self, request, *args, **kwargs):
        membership = self.get_object()
        # Only workspace admins/owners can change roles
        require_workspace_admin(request.user, membership.workspace_id)
        new_role = request.data.get("role")
        if new_role and new_role in ["owner", "admin", "manager", "agent", "viewer"]:
            # Prevent demoting the sole owner to a non-owner role
            if membership.role == "owner" and new_role != "owner":
                other_owners = WorkspaceMembership.objects.filter(
                    workspace_id=membership.workspace_id, role="owner"
                ).exclude(id=membership.id).exists()
                if not other_owners:
                    return api_error(
                        "Cannot demote the sole owner. Assign another owner first.",
                        code="BAD_REQUEST", status_code=400,
                    )
            membership.role = new_role
            membership.save(update_fields=["role"])
        return Response(WorkspaceMembershipSerializer(membership).data)

    def destroy(self, request, *args, **kwargs):
        membership = self.get_object()
        require_workspace_admin(request.user, membership.workspace_id)
        if membership.role == "owner":
            other_owners = WorkspaceMembership.objects.filter(
                workspace_id=membership.workspace_id, role="owner"
            ).exclude(id=membership.id).exists()
            if not other_owners:
                return api_error(
                    "Cannot remove the sole owner of a workspace.",
                    code="BAD_REQUEST", status_code=400,
                )
        return super().destroy(request, *args, **kwargs)


class InviteMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)
        # Only admins/owners can invite new members
        require_workspace_admin(request.user, ws_id)
        email = request.data.get("email")
        role = request.data.get("role", "agent")
        if role not in ["owner", "admin", "manager", "agent", "viewer"]:
            return api_error("Invalid role.", code="BAD_REQUEST", status_code=400)
        from apps.accounts.models import User
        user = User.objects.filter(email=email).first()
        if not user:
            return api_error("User not found. They need to register first.", code="NOT_FOUND", status_code=404)
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace_id=ws_id, user=user,
            defaults={"role": role},
        )
        return Response(WorkspaceMembershipSerializer(membership).data, status=201 if created else 200)
