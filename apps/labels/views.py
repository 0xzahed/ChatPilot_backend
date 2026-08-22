from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from apps.inbox.models import Label
from apps.inbox.serializers import LabelSerializer
from apps.inbox.views import get_user_workspaces


class LabelListView(generics.ListCreateAPIView):
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Label.objects.filter(workspace_id__in=ws_ids)

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class LabelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Label.objects.filter(workspace_id__in=ws_ids)
