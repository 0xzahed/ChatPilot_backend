from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.integrations.models import WebhookEvent
from apps.integrations.serializers import WebhookEventSerializer
from apps.inbox.views import get_user_workspaces


class WebhookEventListView(generics.ListAPIView):
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
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
        ws_ids = get_user_workspaces(self.request.user)
        return WebhookEvent.objects.filter(workspace_id__in=ws_ids)


class WebhookReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = WebhookEvent.objects.filter(id=event_id).first()
        if not event:
            return Response({"error": "Not found."}, status=404)
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(event.id), event.source)
        return Response({"status": "replaying"})
