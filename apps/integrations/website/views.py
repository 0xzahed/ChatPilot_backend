"""Website webchat integration — handles the public-facing chat widget API."""

import secrets
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone

from apps.webchat.models import WebchatConfig, WebchatSession
from apps.workspaces.models import Workspace
from apps.customers.models import Customer, CustomerChannel
from apps.inbox.models import Conversation, Message
from apps.inbox.views import get_user_workspaces


class WebchatConfigView(APIView):
    """Public endpoint to get webchat widget configuration."""

    permission_classes = [AllowAny]

    def get(self, request, workspace_id):
        config = WebchatConfig.objects.filter(workspace_id=workspace_id, is_enabled=True).first()
        if not config:
            return Response({"error": "Webchat not available."}, status=404)
        return Response({
            "title": config.title,
            "welcome_message": config.welcome_message,
            "offline_message": config.offline_message,
            "primary_color": config.primary_color,
            "position": config.position,
            "logo_url": config.logo_url,
            "workspace_id": str(config.workspace_id),
        })


class WebchatInitSessionView(APIView):
    """Initialize a webchat session for a website visitor."""

    permission_classes = [AllowAny]

    def post(self, request, workspace_id):
        config = WebchatConfig.objects.filter(workspace_id=workspace_id, is_enabled=True).first()
        if not config:
            return Response({"error": "Webchat not available."}, status=404)

        session_token = secrets.token_urlsafe(32)
        session = WebchatSession.objects.create(
            workspace_id=workspace_id,
            session_token=session_token,
            visitor_name=request.data.get("name", "Anonymous"),
            visitor_email=request.data.get("email", ""),
            visitor_phone=request.data.get("phone", ""),
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        # Create or find customer
        customer, created = Customer.objects.get_or_create(
            workspace_id=workspace_id,
            name=session.visitor_name,
            defaults={"phone": session.visitor_phone, "email": session.visitor_email},
        )
        if not created and session.visitor_phone and not customer.phone:
            customer.phone = session.visitor_phone
            customer.save(update_fields=["phone"])

        CustomerChannel.objects.get_or_create(
            channel="website", external_id=session_token,
            defaults={"customer": customer, "display_name": session.visitor_name},
        )
        session.customer = customer
        session.save(update_fields=["customer"])

        # Create conversation
        conversation = Conversation.objects.create(
            workspace_id=workspace_id,
            customer=customer,
            channel="website",
            external_id=session_token,
            last_message_at=timezone.now(),
            last_message_preview=config.welcome_message[:100],
        )

        # Welcome message
        Message.objects.create(
            conversation=conversation,
            workspace_id=workspace_id,
            sender_type="system",
            direction="outbound",
            message_type="text",
            content=config.welcome_message,
            status="sent",
        )

        return Response({
            "session_token": session_token,
            "conversation_id": str(conversation.id),
            "welcome_message": config.welcome_message,
        })


class WebchatSendMessageView(APIView):
    """Receive a message from a website visitor."""

    permission_classes = [AllowAny]

    def post(self, request):
        session_token = request.data.get("session_token")
        content = request.data.get("content", "")
        if not session_token or not content:
            return Response({"error": "session_token and content are required."}, status=400)

        session = WebchatSession.objects.filter(session_token=session_token).first()
        if not session:
            return Response({"error": "Invalid session."}, status=404)

        conversation = Conversation.objects.filter(
            workspace=session.workspace, external_id=session_token
        ).first()
        if not conversation:
            return Response({"error": "Conversation not found."}, status=404)

        message = Message.objects.create(
            conversation=conversation,
            workspace=session.workspace,
            sender_type="customer",
            direction="inbound",
            message_type="text",
            content=content,
            status="sent",
        )

        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = content[:100]
        conversation.unread_count += 1
        conversation.save(update_fields=["last_message_at", "last_message_preview", "unread_count"])

        # Broadcast to workspace
        from apps.inbox.consumers import broadcast_new_message, broadcast_workspace_event
        broadcast_new_message(message)
        broadcast_workspace_event(session.workspace_id, "new_message", {
            "conversation_id": str(conversation.id),
        })

        # Trigger AI auto-reply if enabled
        from apps.integrations.website.services import trigger_ai_reply
        trigger_ai_reply.delay(conversation.id, message.id)

        return Response({"message_id": str(message.id), "status": "sent"})


class WebchatMessagesView(APIView):
    """Get messages for a webchat session (polled by the widget)."""

    permission_classes = [AllowAny]

    def get(self, request):
        session_token = request.query_params.get("session_token")
        session = WebchatSession.objects.filter(session_token=session_token).first()
        if not session:
            return Response({"error": "Invalid session."}, status=404)

        conversation = Conversation.objects.filter(
            workspace=session.workspace, external_id=session_token
        ).first()
        if not conversation:
            return Response({"error": "Conversation not found."}, status=404)

        messages = conversation.messages.filter(
            sender_type__in=["system", "ai", "agent"]
        ).order_by("created_at")
        from apps.inbox.serializers import MessageSerializer
        return Response(MessageSerializer(messages, many=True).data)


class WebchatConfigManageView(generics.RetrieveUpdateAPIView):
    """Manage webchat configuration (authenticated)."""

    from apps.webchat.models import WebchatConfig
    from apps.webchat.serializers import WebchatConfigSerializer
    serializer_class = WebchatConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs["workspace_id"]
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            return None
        config, _ = WebchatConfig.objects.get_or_create(workspace_id=ws_id)
        return config
