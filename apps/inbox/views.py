from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.workspaces.models import WorkspaceMembership
from .models import Conversation, Message, MessageAttachment, Label, ConversationLabel
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    MessageSerializer, CreateMessageSerializer, AssignConversationSerializer,
    UpdateConversationSerializer, LabelSerializer,
)
from apps.ai.services.ai_service import AIService


def get_user_workspaces(user):
    """Return workspace IDs the user belongs to."""
    return list(user.workspace_memberships.values_list("workspace_id", flat=True))


class ConversationListView(generics.ListAPIView):
    serializer_class = ConversationListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = Conversation.objects.filter(workspace_id__in=ws_ids).select_related(
            "customer", "assigned_to"
        ).prefetch_related("labels")

        # Filters
        channel = self.request.query_params.get("channel")
        if channel:
            qs = qs.filter(channel=channel)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        handled_by = self.request.query_params.get("handled_by")
        if handled_by:
            qs = qs.filter(handled_by=handled_by)

        is_complaint = self.request.query_params.get("is_complaint")
        if is_complaint == "true":
            qs = qs.filter(is_complaint=True)

        has_order = self.request.query_params.get("has_order")
        if has_order == "true":
            qs = qs.filter(has_order=True)

        assigned = self.request.query_params.get("assigned")
        if assigned == "me":
            qs = qs.filter(assigned_to=self.request.user)
        elif assigned == "unassigned":
            qs = qs.filter(assigned_to__isnull=True)

        unread = self.request.query_params.get("unread")
        if unread == "true":
            qs = qs.filter(unread_count__gt=0)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(customer__name__icontains=search) |
                Q(last_message_preview__icontains=search) |
                Q(customer__phone__icontains=search)
            )

        return qs


class ConversationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ConversationDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "conversation_id"

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Conversation.objects.filter(workspace_id__in=ws_ids).select_related("customer", "assigned_to")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        conversation = serializer.instance
        # Broadcast via channel layer
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conversation)


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs["conversation_id"]
        return Message.objects.filter(conversation_id=conversation_id).prefetch_related("attachments").order_by("created_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Mark conversation as read
        conv = Conversation.objects.filter(id=self.kwargs["conversation_id"]).first()
        if conv and conv.unread_count > 0:
            conv.unread_count = 0
            conv.save(update_fields=["unread_count"])
        return response


class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)

        serializer = CreateMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_note = serializer.validated_data.get("is_note", False)
        message = Message.objects.create(
            conversation=conv,
            workspace=conv.workspace,
            sender_type="system" if is_note else "agent",
            direction="outbound",
            message_type="note" if is_note else serializer.validated_data.get("message_type", "text"),
            content=serializer.validated_data["content"],
            sent_by=request.user,
            reply_to_id=serializer.validated_data.get("reply_to"),
            status="sent",
        )

        # Update conversation preview
        conv.last_message_at = timezone.now()
        conv.last_message_preview = serializer.validated_data["content"][:100]
        conv.status = "open"
        conv.save(update_fields=["last_message_at", "last_message_preview", "status"])

        # Broadcast via websocket
        from .consumers import broadcast_new_message
        broadcast_new_message(message)

        return Response(MessageSerializer(message).data, status=201)


class AssignConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)
        serializer = AssignConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.accounts.models import User
        agent = User.objects.filter(id=serializer.validated_data["assigned_to"]).first()
        if not agent:
            return Response({"error": "Agent not found."}, status=404)
        conv.assigned_to = agent
        if conv.handled_by == "unassigned":
            conv.handled_by = "human"
        conv.save(update_fields=["assigned_to", "handled_by"])

        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return Response(ConversationDetailSerializer(conv).data)


class CloseConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)
        conv.status = "closed"
        conv.save(update_fields=["status"])
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return Response({"detail": "Conversation closed."})


class ReopenConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)
        conv.status = "open"
        conv.save(update_fields=["status"])
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return Response({"detail": "Conversation reopened."})


class MarkUnreadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)
        conv.unread_count = 1
        conv.save(update_fields=["unread_count"])
        return Response({"detail": "Marked as unread."})


class AISuggestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Conversation not found."}, status=404)
        ai_service = AIService(conv.workspace)
        result = ai_service.generate_suggestion(conv)
        return Response(result)


class ConversationLabelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Not found."}, status=404)
        return Response(LabelSerializer(conv.labels.all(), many=True).data)

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Not found."}, status=404)
        label_id = request.data.get("label_id")
        label = Label.objects.filter(id=label_id, workspace=conv.workspace).first()
        if not label:
            return Response({"error": "Label not found."}, status=404)
        ConversationLabel.objects.get_or_create(conversation=conv, label=label)
        return Response(LabelSerializer(conv.labels.all(), many=True).data, status=201)

    def delete(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Not found."}, status=404)
        label_id = request.data.get("label_id")
        ConversationLabel.objects.filter(conversation=conv, label_id=label_id).delete()
        return Response(status=204)


class LabelListCreateView(generics.ListCreateAPIView):
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Label.objects.filter(workspace_id__in=ws_ids)

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=400)
        serializer.save(workspace_id=ws_id)


class LabelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Label.objects.filter(workspace_id__in=ws_ids)


class TypingIndicatorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = Conversation.objects.filter(id=conversation_id).first()
        if not conv:
            return Response({"error": "Not found."}, status=404)
        from .consumers import broadcast_typing
        broadcast_typing(conv, request.user, request.data.get("is_typing", True))
        return Response({"detail": "ok"})
