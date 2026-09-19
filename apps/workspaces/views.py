from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Workspace, WorkspaceMembership, WorkspaceSettings
from common.api_response import api_error, api_success, api_paginated
from common.permissions import require_workspace_admin
from .serializers import (
    WorkspaceSerializer, WorkspaceMembershipSerializer,
    CreateWorkspaceSerializer, WorkspaceSettingsSerializer,
)


class WorkspaceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = request.user.workspace_memberships.select_related("workspace").all()
        workspaces = [m.workspace for m in memberships]
        return api_success(data=WorkspaceSerializer(workspaces, many=True).data, message="Workspaces fetched")

    def post(self, request):
        serializer = CreateWorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = Workspace.objects.create(
            name=serializer.validated_data["name"],
            slug=serializer.validated_data["slug"],
            owner=request.user,
        )
        WorkspaceSettings.objects.create(workspace=workspace)
        membership = WorkspaceMembership.objects.create(
            workspace=workspace, user=request.user, role="owner",
        )
        return api_success(data={
            "workspace": WorkspaceSerializer(workspace).data,
            "membership": WorkspaceMembershipSerializer(membership).data,
        }, message="Workspace created", status_code=201)


class WorkspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return Workspace.objects.filter(memberships__user=self.request.user)


class WorkspaceMembersView(generics.ListCreateAPIView):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]
    queryset = WorkspaceMembership.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        workspace_id = self.kwargs["workspace_id"]
        # Only members may enumerate a workspace's member list — otherwise
        # any authenticated user could enumerate other tenants' teams.
        return WorkspaceMembership.objects.filter(
            workspace_id=workspace_id,
            workspace__memberships__user=self.request.user,
        )

    def create(self, request, **kwargs):
        workspace_id = kwargs["workspace_id"]
        workspace = Workspace.objects.filter(id=workspace_id, memberships__user=request.user).first()
        if not workspace:
            return api_error("Workspace not found.", code="NOT_FOUND", status_code=404)
        # Only admins/owners can add members
        require_workspace_admin(request.user, workspace_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.accounts.models import User
        user = User.objects.filter(email=serializer.validated_data.get("user_email")).first()
        if not user:
            return api_error("User not found.", code="NOT_FOUND", status_code=404)
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=workspace, user=user,
            defaults={"role": serializer.validated_data.get("role", "agent")},
        )
        return api_success(data=WorkspaceMembershipSerializer(membership).data, message="Member added" if created else "Member exists", status_code=201 if created else 200)


class WorkspaceSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        workspace_id = self.kwargs["workspace_id"]
        # Require membership before reading or mutating workspace settings.
        if not WorkspaceMembership.objects.filter(
            workspace_id=workspace_id, user=self.request.user
        ).exists():
            from rest_framework.exceptions import NotFound
            raise NotFound("Workspace not found.")
        ws, _ = WorkspaceSettings.objects.get_or_create(workspace_id=workspace_id)
        return ws
