from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import WebchatConfig, WebchatSession
from .serializers import WebchatConfigSerializer
from apps.inbox.views import get_user_workspaces
from apps.inbox.models import Conversation, Message
from apps.customers.models import Customer, CustomerChannel
from django.utils import timezone
import uuid
from common.api_response import api_error, api_success, api_paginated


class WebchatConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = WebchatConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        ws_id = self.kwargs.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            return None
        config, _ = WebchatConfig.objects.get_or_create(workspace_id=ws_id)
        return config


class WebchatPublicConfigView(APIView):
    """Public endpoint — returns webchat config for embedding on external websites."""
    permission_classes = [AllowAny]

    def get(self, request, workspace_id):
        try:
            config = WebchatConfig.objects.get(workspace_id=workspace_id, is_enabled=True)
        except WebchatConfig.DoesNotExist:
            return api_error("Webchat not enabled", code="NOT_FOUND", status_code=404)

        return api_success(data={
            "workspace_id": str(config.workspace_id),
            "title": config.title,
            "welcome_message": config.welcome_message,
            "primary_color": config.primary_color,
            "position": config.position,
            "logo_url": config.logo_url,
        }, message="Config fetched")


class WebchatSessionView(APIView):
    """Create or retrieve a webchat session for a website visitor."""
    permission_classes = [AllowAny]

    def post(self, request):
        workspace_id = request.data.get("workspace_id")
        session_token = request.data.get("session_token")
        visitor_name = request.data.get("visitor_name", "Anonymous")
        visitor_email = request.data.get("visitor_email", "")
        visitor_phone = request.data.get("visitor_phone", "")

        # Check if session exists
        if session_token:
            session = WebchatSession.objects.filter(session_token=session_token).first()
            if session:
                # Update visitor info if provided
                if visitor_name and visitor_name != "Anonymous":
                    session.visitor_name = visitor_name
                    session.save(update_fields=["visitor_name"])
                if visitor_email:
                    session.visitor_email = visitor_email
                    session.save(update_fields=["visitor_email"])
                if visitor_phone:
                    session.visitor_phone = visitor_phone
                    session.save(update_fields=["visitor_phone"])
                return api_success(data={
                    "session_token": session.session_token,
                    "visitor_name": session.visitor_name,
        }, message="Session created")

        # Create new session
        token = str(uuid.uuid4())
        session = WebchatSession.objects.create(
            workspace_id=workspace_id,
            session_token=token,
            visitor_name=visitor_name,
            visitor_email=visitor_email,
            visitor_phone=visitor_phone,
        )
        return api_success(data={
            "session_token": session.session_token,
            "visitor_name": session.visitor_name,
        }, message="Session created", status_code=201)


class WebchatMessageView(APIView):
    """Receive a message from a website visitor and create a conversation."""
    permission_classes = [AllowAny]

    def post(self, request):
        workspace_id = request.data.get("workspace_id")
        session_token = request.data.get("session_token")
        content = request.data.get("content", "").strip()

        if not content:
            return api_error("Message content required.", code="BAD_REQUEST", status_code=400)

        # Get or create session
        session = None
        if session_token:
            session = WebchatSession.objects.filter(session_token=session_token).first()

        if not session:
            token = str(uuid.uuid4())
            session = WebchatSession.objects.create(
                workspace_id=workspace_id,
                session_token=token,
                visitor_name="Anonymous",
            )

        # Find or create customer
        channel = CustomerChannel.objects.filter(
            channel="website", external_id=session.session_token
        ).first()
        if channel:
            customer = channel.customer
        else:
            customer = Customer.objects.create(
                workspace_id=workspace_id,
                name=session.visitor_name or "Website Visitor",
            )
            CustomerChannel.objects.create(
                customer=customer,
                channel="website",
                external_id=session.session_token,
                display_name=session.visitor_name,
            )

        # Find or create conversation
        conv = Conversation.objects.filter(
            workspace_id=workspace_id, channel="website",
            external_id=session.session_token, status="open",
        ).first()
        if not conv:
            conv = Conversation.objects.create(
                workspace_id=workspace_id,
                customer=customer,
                channel="website",
                status="open",
                handled_by="unassigned",
                external_id=session.session_token,
            )

        # Create message
        msg = Message.objects.create(
            conversation=conv,
            workspace_id=workspace_id,
            sender_type="customer",
            direction="inbound",
            message_type="text",
            content=content,
            external_id=f"webchat_{session.session_token}_{msg_id()}",
            status="sent",
        )

        # Update conversation
        conv.last_message_at = timezone.now()
        conv.last_message_preview = content[:100]
        conv.unread_count += 1
        conv.save(update_fields=["last_message_at", "last_message_preview", "unread_count"])

        # Broadcast via WebSocket
        try:
            from apps.inbox.consumers import broadcast_new_message, broadcast_workspace_event
            broadcast_new_message(msg)
            broadcast_workspace_event(
                str(workspace_id), "new_message",
                {"conversation_id": str(conv.id), "channel": "website"},
            )
        except Exception:
            pass

        # Auto-reply if AI is enabled
        auto_reply = None
        if conv.ai_enabled:
            try:
                from apps.ai.services.ai_service import AIService
                ai_service = AIService(conv.workspace)
                if ai_service.settings.mode in ("auto_reply", "hybrid"):
                    result = ai_service.auto_reply(conv, msg)
                    if result:
                        auto_reply = result
            except Exception:
                pass

        return api_success(data={
            "status": "sent",
            "session_token": session.session_token,
            "auto_reply": auto_reply,
        }, message="Message sent", status_code=201)


def msg_id():
    import random
    return str(random.randint(100000, 999999))
