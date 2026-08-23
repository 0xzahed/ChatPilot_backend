from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.workspaces.models import WorkspaceMembership, Workspace
from apps.workspaces.serializers import WorkspaceMembershipSerializer
from apps.inbox.views import get_user_workspaces


class TeamListView(generics.ListAPIView):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return WorkspaceMembership.objects.filter(workspace_id__in=ws_ids).select_related("user", "workspace")


class TeamMemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkspaceMembershipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return WorkspaceMembership.objects.filter(workspace_id__in=ws_ids)

    def patch(self, request, *args, **kwargs):
        membership = self.get_object()
        new_role = request.data.get("role")
        if new_role and new_role in ["owner", "admin", "manager", "agent", "viewer"]:
            membership.role = new_role
            membership.save(update_fields=["role"])
        return Response(WorkspaceMembershipSerializer(membership).data)


class InviteMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=400)
        email = request.data.get("email")
        role = request.data.get("role", "agent")
        from apps.accounts.models import User
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"error": "User not found. They need to register first."}, status=404)
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace_id=ws_id, user=user,
            defaults={"role": role},
        )
        return Response(WorkspaceMembershipSerializer(membership).data, status=201 if created else 200)
