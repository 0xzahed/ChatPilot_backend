from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import AISettings, AIInstructions, AIEvent, AIUsage
from .serializers import (
    AISettingsSerializer, AIInstructionsSerializer,
    AIEventSerializer, AIUsageSerializer,
)
from apps.inbox.views import get_user_workspaces


class AISettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = AISettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs["workspace_id"]
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        settings_obj, _ = AISettings.objects.get_or_create(workspace_id=ws_id)
        return settings_obj


class AIInstructionsView(generics.RetrieveUpdateAPIView):
    serializer_class = AIInstructionsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs["workspace_id"]
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        instructions, _ = AIInstructions.objects.get_or_create(workspace_id=ws_id)
        return instructions


class AIEventListView(generics.ListAPIView):
    serializer_class = AIEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return AIEvent.objects.filter(workspace_id__in=ws_ids)


class AIUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if workspace_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=403)
        usage = AIUsage.objects.filter(workspace_id=workspace_id).order_by("-date")[:30]
        return Response(AIUsageSerializer(usage, many=True).data)
