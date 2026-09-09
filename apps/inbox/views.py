from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
import logging

from apps.workspaces.models import WorkspaceMembership
from .models import Conversation, Message, MessageAttachment, Label, ConversationLabel
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    MessageSerializer, CreateMessageSerializer, AssignConversationSerializer,
    UpdateConversationSerializer, LabelSerializer,
)

logger = logging.getLogger(__name__)
from apps.ai.services.ai_service import AIService
from common.api_response import api_error, api_success, api_paginated


def get_user_workspaces(user):
    """Return workspace IDs (as strings) the user belongs to."""
    return [str(pk) for pk in user.workspace_memberships.values_list("workspace_id", flat=True)]


def get_conversation_for_user(user, conversation_id):
    """Fetch a conversation only if the user is a member of its workspace."""
    ws_ids = get_user_workspaces(user)
    return Conversation.objects.filter(id=conversation_id, workspace_id__in=ws_ids).first()


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
        ws_ids = get_user_workspaces(self.request.user)
        return Message.objects.filter(
            conversation_id=conversation_id,
            conversation__workspace_id__in=ws_ids,
        ).prefetch_related("attachments").order_by("created_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Mark conversation as read (only if user has access)
        conv = get_conversation_for_user(request.user, self.kwargs["conversation_id"])
        if conv and conv.unread_count > 0:
            conv.unread_count = 0
            conv.save(update_fields=["unread_count"])
        return response


class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)

        serializer = CreateMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_note = serializer.validated_data.get("is_note", False)
        content = serializer.validated_data["content"]
        msg_type = serializer.validated_data.get("message_type", "text")

        message = Message.objects.create(
            conversation=conv,
            workspace=conv.workspace,
            sender_type="system" if is_note else "agent",
            direction="outbound",
            message_type="note" if is_note else msg_type,
            content=content,
            sent_by=request.user,
            reply_to_id=serializer.validated_data.get("reply_to"),
            status="sent",
        )

        # If this is a channel conversation (not a note), send via the provider
        if not is_note and conv.channel != "website":
            try:
                _send_to_channel(conv, content, msg_type)
                message.status = "delivered"
                message.save(update_fields=["status"])
            except Exception as e:
                logger.error(f"Failed to send message to {conv.channel}: {e}")
                message.status = "failed"
                message.save(update_fields=["status"])
                # Still return success since message is saved in DB

        # Update conversation preview
        conv.last_message_at = timezone.now()
        conv.last_message_preview = content[:100]
        conv.status = "open"
        # Agent replied → mark as read
        if not is_note:
            conv.unread_count = 0
        conv.save(update_fields=["last_message_at", "last_message_preview", "status", "unread_count"])

        # Broadcast via websocket — both conversation group and workspace group
        from .consumers import broadcast_new_message, broadcast_workspace_event, broadcast_conversation_update
        broadcast_new_message(message)
        broadcast_conversation_update(conv)
        # Also notify workspace so conversation list refreshes
        broadcast_workspace_event(
            str(conv.workspace_id), "new_message",
            {"conversation_id": str(conv.id), "channel": conv.channel},
        )

        return Response(MessageSerializer(message).data, status=201)


def _send_to_channel(conversation, content, message_type="text"):
    """Send a message to the external channel (Facebook, WhatsApp, etc.)."""
    from apps.customers.models import CustomerChannel
    from apps.integrations.models import Integration

    # Get the customer's external ID on this channel
    channel = CustomerChannel.objects.filter(
        customer=conversation.customer, channel=conversation.channel
    ).first()
    if not channel:
        raise Exception(f"No channel identity found for customer on {conversation.channel}")

    # Get the integration
    integration = Integration.objects.filter(
        workspace=conversation.workspace,
        integration_type=conversation.channel,
        is_active=True,
    ).first()
    if not integration:
        raise Exception(f"No active {conversation.channel} integration found")

    # Get provider and send
    if conversation.channel == "facebook":
        from apps.integrations.facebook.client import get_facebook_provider
        provider = get_facebook_provider(integration)
    elif conversation.channel == "instagram":
        from apps.integrations.instagram.client import get_instagram_provider
        provider = get_instagram_provider(integration)
    elif conversation.channel == "whatsapp":
        from apps.integrations.whatsapp.client import get_whatsapp_provider
        provider = get_whatsapp_provider(integration)
    else:
        return  # Website/webchat doesn't need external send

    result = provider.send_message(
        recipient_id=channel.external_id,
        content=content,
        message_type=message_type,
        page_id=conversation.config.get("page_id", ""),
    )
    if not result.success:
        raise Exception("Provider returned failure")
    return result


class AssignConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        serializer = AssignConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.accounts.models import User
        agent = User.objects.filter(id=serializer.validated_data["assigned_to"]).first()
        if not agent:
            return api_error("Agent not found.", code="NOT_FOUND", status_code=404)
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
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.status = "closed"
        conv.save(update_fields=["status"])
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return api_success(message="Conversation closed")


class ReopenConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.status = "open"
        conv.save(update_fields=["status"])
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return api_success(message="Conversation reopened")


class MarkUnreadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.unread_count = 1
        conv.save(update_fields=["unread_count"])
        return api_success(message="Marked as unread")


class AISuggestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        ai_service = AIService(conv.workspace)
        result = ai_service.generate_suggestion(conv)
        return Response(result)


class ConversationLabelsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        return Response(LabelSerializer(conv.labels.all(), many=True).data)

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        label_id = request.data.get("label_id")
        label = Label.objects.filter(id=label_id, workspace=conv.workspace).first()
        if not label:
            return api_error("Label not found.", code="NOT_FOUND", status_code=404)
        ConversationLabel.objects.get_or_create(conversation=conv, label=label)
        return Response(LabelSerializer(conv.labels.all(), many=True).data, status=201)

    def delete(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
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
        if str(ws_id) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)
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
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        from .consumers import broadcast_typing
        broadcast_typing(conv, request.user, request.data.get("is_typing", True))
        return api_success(message="OK")
