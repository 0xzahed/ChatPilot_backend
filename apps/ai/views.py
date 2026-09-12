from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from api_response_toolkit.exceptions import ForbiddenError
from .models import AISettings, AIInstructions, AIEvent, AIUsage
from .serializers import (
    AISettingsSerializer, AIInstructionsSerializer,
    AIEventSerializer, AIUsageSerializer,
)
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated
from apps.ai.models import AIEvent


class AISettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = AISettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs["workspace_id"]
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            raise ForbiddenError("Invalid workspace.")
        settings_obj, _ = AISettings.objects.get_or_create(workspace_id=ws_id)
        return settings_obj


class AIInstructionsView(generics.RetrieveUpdateAPIView):
    serializer_class = AIInstructionsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs["workspace_id"]
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            raise ForbiddenError("Invalid workspace.")
        instructions, _ = AIInstructions.objects.get_or_create(workspace_id=ws_id)
        return instructions


class AIEventListView(generics.ListAPIView):
    queryset = AIEvent.objects.none()
    serializer_class = AIEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return AIEvent.objects.filter(workspace_id__in=ws_ids)


class AIUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if str(workspace_id) not in ws_ids:
            return api_error("Invalid workspace.", code="FORBIDDEN", status_code=403)
        usage = AIUsage.objects.filter(workspace_id=workspace_id).order_by("-date")[:30]
        return api_success(data=AIUsageSerializer(usage, many=True).data, message="Usage fetched")


class AITestView(APIView):
    """Test AI assistant with a sample message using current settings."""

    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if str(workspace_id) not in ws_ids:
            return api_error("Invalid workspace.", code="FORBIDDEN", status_code=403)

        message = request.data.get("message", "").strip()
        if not message:
            return api_error("Message is required.", code="BAD_REQUEST", status_code=400)

        from apps.workspaces.models import Workspace
        from apps.ai.services.ai_service import AIService

        try:
            workspace = Workspace.objects.get(id=workspace_id)
        except Workspace.DoesNotExist:
            return api_error("Workspace not found.", code="NOT_FOUND", status_code=404)

        settings_obj, _ = AISettings.objects.get_or_create(workspace=workspace)
        instructions, _ = AIInstructions.objects.get_or_create(workspace=workspace)

        # Build system prompt from instructions (same as AIService)
        ai_service = AIService(workspace)
        system_prompt = ai_service._build_system_prompt()

        # Build messages for the AI
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        # Call the real provider
        try:
            response = ai_service.provider.chat_completion(
                messages=messages,
                temperature=settings_obj.temperature,
                max_tokens=settings_obj.max_tokens,
            )

            # Check if the response is an error
            if response.text.startswith("[AI Error:"):
                return api_success(data={
                    "response": response.text,
                    "provider": settings_obj.provider,
                    "model": settings_obj.model_name,
                    "mode": settings_obj.mode,
                    "error": True,
                }, status=200)  # Return 200 so frontend can display the error message

            return api_success(data={
                "response": response.text,
                "provider": settings_obj.provider,
                "model": response.model or settings_obj.model_name,
                "mode": settings_obj.mode,
                "tokens_input": response.tokens_input,
                "tokens_output": response.tokens_output,
                "confidence": response.confidence,
        }, message="AI response")
        except Exception as e:
            return api_error(f"AI Error: {str(e)}", code="INTERNAL_ERROR", status_code=500)
