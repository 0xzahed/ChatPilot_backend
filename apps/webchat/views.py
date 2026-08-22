from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import WebchatConfig
from .serializers import WebchatConfigSerializer
from apps.inbox.views import get_user_workspaces


class WebchatConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = WebchatConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            return None
        config, _ = WebchatConfig.objects.get_or_create(workspace_id=ws_id)
        return config
