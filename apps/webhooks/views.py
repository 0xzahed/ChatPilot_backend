from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.integrations.models import WebhookEvent
from apps.integrations.serializers import WebhookEventSerializer
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated


class WebhookEventListView(generics.ListAPIView):
    queryset = WebhookEvent.objects.none()
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        qs = WebhookEvent.objects.filter(workspace_id__in=ws_ids)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source=source)
        return qs


class WebhookEventDetailView(generics.RetrieveAPIView):
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return WebhookEvent.objects.filter(workspace_id__in=ws_ids)


class WebhookReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        ws_ids = get_user_workspaces(request.user)
        event = WebhookEvent.objects.filter(id=event_id, workspace_id__in=ws_ids).first()
        if not event:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(event.id), event.source)
        return api_success(message="Replaying")
