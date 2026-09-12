from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import AutomationRule, Comment
from .serializers import AutomationRuleSerializer, CommentSerializer
from apps.inbox.views import get_user_workspaces
from apps.automation.models import AutomationRule
from apps.automation.models import Comment


class AutomationRuleListView(generics.ListCreateAPIView):
    queryset = AutomationRule.objects.none()
    serializer_class = AutomationRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return AutomationRule.objects.filter(workspace_id__in=ws_ids)

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class AutomationRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AutomationRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return AutomationRule.objects.filter(workspace_id__in=ws_ids)


class CommentListView(generics.ListAPIView):
    queryset = Comment.objects.none()
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        qs = Comment.objects.filter(workspace_id__in=ws_ids)
        is_replied = self.request.query_params.get("is_replied")
        if is_replied == "false":
            qs = qs.filter(is_replied=False)
        return qs
