from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Workspace, WorkspaceMembership, WorkspaceSettings
from .serializers import (
    WorkspaceSerializer, WorkspaceMembershipSerializer,
    CreateWorkspaceSerializer, WorkspaceSettingsSerializer,
)


class WorkspaceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = request.user.workspace_memberships.select_related("workspace").all()
        workspaces = [m.workspace for m in memberships]
        return Response(WorkspaceSerializer(workspaces, many=True).data)

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
        return Response({
            "workspace": WorkspaceSerializer(workspace).data,
            "membership": WorkspaceMembershipSerializer(membership).data,
        }, status=status.HTTP_201_CREATED)


class WorkspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.filter(memberships__user=self.request.user)


class WorkspaceMembersView(generics.ListCreateAPIView):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        workspace_id = self.kwargs["workspace_id"]
        return WorkspaceMembership.objects.filter(workspace_id=workspace_id)

    def create(self, request, **kwargs):
        workspace_id = kwargs["workspace_id"]
        workspace = Workspace.objects.filter(id=workspace_id, memberships__user=request.user).first()
        if not workspace:
            return Response({"error": "Workspace not found."}, status=404)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.accounts.models import User
        user = User.objects.filter(email=serializer.validated_data.get("user_email")).first()
        if not user:
            return Response({"error": "User not found."}, status=404)
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=workspace, user=user,
            defaults={"role": serializer.validated_data.get("role", "agent")},
        )
        return Response(WorkspaceMembershipSerializer(membership).data, status=201 if created else 200)


class WorkspaceSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = WorkspaceSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        workspace_id = self.kwargs["workspace_id"]
        ws, _ = WorkspaceSettings.objects.get_or_create(workspace_id=workspace_id)
        return ws
