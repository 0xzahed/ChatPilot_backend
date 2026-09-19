from django.db.models import Q, Count, Prefetch, Subquery, OuterRef, CharField
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
import logging

from apps.workspaces.models import WorkspaceMembership
from apps.customers.models import CustomerChannel
from .models import Conversation, Message, MessageAttachment, Label, ConversationLabel
from .serializers import (
    ConversationListSerializer, ConversationDetailSerializer,
    MessageSerializer, CreateMessageSerializer, AssignConversationSerializer,
    UpdateConversationSerializer, LabelSerializer,
)

logger = logging.getLogger(__name__)
from apps.ai.services.ai_service import AIService
from common.api_response import api_error, api_success, api_paginated
from apps.inbox.models import Conversation
from apps.inbox.models import Message
from apps.inbox.models import Label


def get_user_workspaces(user):
    """Return workspace IDs (as strings) the user belongs to."""
    return [str(pk) for pk in user.workspace_memberships.values_list("workspace_id", flat=True)]


def get_conversation_for_user(user, conversation_id):
    """Fetch a conversation only if the user is a member of its workspace."""
    ws_ids = get_user_workspaces(user)
    return Conversation.objects.filter(id=conversation_id, workspace_id__in=ws_ids).first()


class ConversationListView(generics.ListAPIView):
    queryset = Conversation.objects.none()
    serializer_class = ConversationListSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Build a page_id → page_name map from all connected Facebook integrations
        # to avoid N+1 queries when serializing page_name per conversation
        ws_ids = get_user_workspaces(self.request.user)
        from apps.integrations.models import Integration
        page_map = {}
        for integration in Integration.objects.filter(
            workspace_id__in=ws_ids,
            integration_type="facebook",
            status="connected",
        ):
            for page in (integration.config or {}).get("connected_pages", []):
                page_map[page.get("page_id", "")] = page.get("page_name", "")
        context["_fb_page_map"] = page_map
        return context

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        # Subquery to get the channel profile_url for this conversation's channel
        # This avoids N+1 queries when serializing customer avatars
        channel_avatar_sq = CustomerChannel.objects.filter(
            customer=OuterRef("customer_id"),
            channel=OuterRef("channel"),
        ).values("profile_url")[:1]

        qs = Conversation.objects.filter(workspace_id__in=ws_ids).select_related(
            "customer", "assigned_to"
        ).prefetch_related("labels").annotate(
            _channel_avatar=Subquery(channel_avatar_sq, output_field=CharField()),
        )

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

        # Filter by Facebook Page ID
        page_id = self.request.query_params.get("page_id")
        if page_id:
            qs = qs.filter(config__page_id=page_id)

        return qs

    def list(self, request, *args, **kwargs):
        from rest_framework.exceptions import NotFound
        try:
            response = super().list(request, *args, **kwargs)
        except NotFound:
            # Local page out of range — treat as empty so merged iedu pages
            # (which may have many more pages) still serve correctly.
            response = None
        # Merge live iedu support-chat conversations (proxy — not stored in DB)
        channel = request.query_params.get("channel")
        if channel and channel != "website":
            if response is None:
                raise NotFound()
            return response
        from apps.integrations.iedu.proxy import client_for_user, list_conversations
        client = client_for_user(request.user)
        if not client:
            if response is None:
                raise NotFound()
            return response
        try:
            page = int(request.query_params.get("page", 1) or 1)
            limit = int(request.query_params.get("limit", 20) or 20)
            items, iedu_meta = list_conversations(
                client,
                page=page,
                limit=limit,
                search=request.query_params.get("search", ""),
                status=request.query_params.get("status", ""),
                unread=request.query_params.get("unread") == "true",
            )
        except Exception:
            if response is None:
                raise NotFound()
            return response

        # The toolkit paginator renders `data` from the queryset — rebuild the
        # envelope ourselves so merged iedu items reach the client.
        rd = response.data if response is not None else {}
        if isinstance(rd, dict):
            local_items = rd.get("results") or rd.get("data") or []
            if not isinstance(local_items, list):
                local_items = []
            local_count = rd.get("count") or (rd.get("pagination") or {}).get("total") or len(local_items)
        else:
            local_items = list(rd or [])
            local_count = len(local_items)
        merged = list(local_items) + items
        merged.sort(key=lambda c: c.get("last_message_at") or "", reverse=True)
        total = local_count + (iedu_meta.get("total_count") or len(items))
        return Response({
            "success": True,
            "message": "Success",
            "data": merged,
            "results": merged,
            "count": total,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": (total + limit - 1) // limit if limit else 0,
            },
        })


class ConversationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ConversationDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "conversation_id"

    def retrieve(self, request, *args, **kwargs):
        conv_id = self.kwargs["conversation_id"]
        if str(conv_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, get_detail
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            conv, _ = get_detail(client, str(conv_id).removeprefix("iedu_"))
            if not conv:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            conv["customer_detail"] = None
            return api_success(data=conv)
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        conv_id = self.kwargs["conversation_id"]
        if str(conv_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, iedu_pk
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            status_val = request.data.get("status")
            if status_val:
                from apps.integrations.iedu.actions import _STATUS_MAP
                import httpx
                target = _STATUS_MAP.get(status_val)
                if target:
                    try:
                        client.set_status(iedu_pk(conv_id), target)
                    except httpx.HTTPStatusError:
                        if target == "done":
                            client.set_status(iedu_pk(conv_id), "archived")
            return self.retrieve(request, *args, **kwargs)
        return super().update(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Conversation.objects.filter(workspace_id__in=ws_ids).select_related("customer", "assigned_to")

    def perform_update(self, serializer):
        super().perform_update(serializer)
        conversation = serializer.instance
        if "status" in serializer.validated_data:
            from apps.integrations.iedu.actions import push_status
            push_status(conversation, conversation.status)
        # Broadcast via channel layer
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conversation)


class MessageListView(generics.ListAPIView):
    queryset = Message.objects.none()
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        conversation_id = self.kwargs["conversation_id"]
        ws_ids = get_user_workspaces(self.request.user)
        return Message.objects.filter(
            conversation_id=conversation_id,
            conversation__workspace_id__in=ws_ids,
        ).prefetch_related("attachments").order_by("created_at")

    def list(self, request, *args, **kwargs):
        conv_id = self.kwargs["conversation_id"]
        if str(conv_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, get_detail, iedu_pk
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            _, msgs = get_detail(client, iedu_pk(conv_id))
            try:
                client.mark_read(iedu_pk(conv_id))
            except Exception:
                pass
            return Response({"count": len(msgs), "next": None, "previous": None, "results": msgs})
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
        if str(conversation_id).startswith("iedu_"):
            return self._post_iedu(request, conversation_id)
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

        # Internal notes sync to iedu as admin notes (same as their panel)
        if is_note:
            from apps.integrations.iedu.actions import push_note
            push_note(conv, content)

        # If this is a channel conversation (not a note), send via the provider
        # (website convs are skipped unless they are iedu-bridged)
        if not is_note and (conv.channel != "website" or conv.config.get("bridge") == "iedu"):
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

    def _post_iedu(self, request, conversation_id):
        """Send a reply/note on an iedu-bridged conversation — proxied to
        iedu's admin API, nothing stored locally."""
        from apps.integrations.iedu.proxy import client_for_user, iedu_pk, msg_to_cp
        client = client_for_user(request.user)
        if not client:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        content = (request.data.get("content") or "").strip()
        if not content:
            return api_error("Content is required.", code="VALIDATION", status_code=400)
        pk = iedu_pk(conversation_id)
        try:
            if request.data.get("is_note"):
                resp = client.add_note(pk, content)
                return api_success(data=resp, message="Note added")
            resp = client.reply(pk, content)
        except Exception as e:
            return api_error(f"iedu send failed: {e}", code="SEND_FAILED", status_code=502)
        # iedu returns the created staff message — transform to our shape
        msg_data = (resp.get("data") or {}) if isinstance(resp, dict) else {}
        if msg_data.get("id"):
            data = msg_to_cp(msg_data, pk)
        else:
            data = {
                "id": f"iedu_msg_local_{pk}",
                "conversation": conversation_id,
                "sender_type": "agent", "direction": "outbound",
                "message_type": "text", "content": content, "status": "delivered",
                "attachments": [], "sender_name": "You", "sent_by": None,
                "reply_to": None, "ai_metadata": {},
            }
        return api_success(data=data, message="Message sent")


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
    elif conversation.channel == "website" and conversation.config.get("bridge") == "iedu":
        from apps.integrations.iedu.client import get_iedu_client
        client = get_iedu_client(conversation.workspace)
        if not client:
            raise Exception("iedu integration not configured")
        client.reply(str(conversation.external_id).removeprefix("iedu_"), content)
        return
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
        if str(conversation_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, iedu_pk
            import httpx
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            try:
                client.set_status(iedu_pk(conversation_id), "done")
            except httpx.HTTPStatusError:
                client.set_status(iedu_pk(conversation_id), "archived")
            return api_success(message="Conversation closed")
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.status = "closed"
        conv.save(update_fields=["status"])
        from apps.integrations.iedu.actions import push_status
        push_status(conv, "closed")
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return api_success(message="Conversation closed")


class ReopenConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        if str(conversation_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, iedu_pk
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            client.set_status(iedu_pk(conversation_id), "open")
            return api_success(message="Conversation reopened")
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.status = "open"
        conv.save(update_fields=["status"])
        from apps.integrations.iedu.actions import push_status
        push_status(conv, "open")
        from .consumers import broadcast_conversation_update
        broadcast_conversation_update(conv)
        return api_success(message="Conversation reopened")


class MarkUnreadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        if str(conversation_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import client_for_user, iedu_pk
            client = client_for_user(request.user)
            if not client:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            client.mark_unread(iedu_pk(conversation_id))
            return api_success(message="Marked as unread")
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)
        conv.unread_count = 1
        conv.save(update_fields=["unread_count"])
        from apps.integrations.iedu.actions import push_unread
        push_unread(conv)
        return api_success(message="Marked as unread")


# ─── Attachment upload security policy ────────────────────────
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".txt", ".csv", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".zip",
}
ALLOWED_ATTACHMENT_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "audio/mpeg", "video/mp4", "application/zip",
    "application/x-zip-compressed", "application/octet-stream",
}
# Magic-byte signatures for the common binary types (prefix match)
_ATTACHMENT_MAGIC = {
    ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"], ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"], ".pdf": [b"%PDF"], ".zip": [b"PK\x03\x04"],
    ".mp3": [b"ID3", b"\xff\xfb"], ".mp4": [b"\x00\x00\x00"],
}


def _validate_attachment(uploaded) -> str | None:
    """Return an error message if the file fails policy checks, else None."""
    import os

    if uploaded.size > MAX_ATTACHMENT_SIZE:
        return "File too large (max 10 MB)."

    name = os.path.basename(uploaded.name or "file")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return f"File type '{ext or 'unknown'}' is not allowed."
    # SVG is deliberately excluded — inline SVG can carry script payloads.
    if ext == ".svg":
        return "SVG files are not allowed."

    mime = getattr(uploaded, "content_type", "") or ""
    if mime and mime not in ALLOWED_ATTACHMENT_MIME:
        return f"MIME type '{mime}' is not allowed."

    # Magic-byte validation for binary types that declare it
    signatures = _ATTACHMENT_MAGIC.get(ext)
    if signatures:
        head = uploaded.read(512)
        uploaded.seek(0)
        if not any(head.startswith(sig) for sig in signatures):
            return "File content does not match its extension."
    return None


class ConversationAttachmentUploadView(APIView):
    """POST /api/conversations/<id>/attachments/ — upload a file as an
    outbound agent message attachment."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, conversation_id):
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            if str(conversation_id).startswith("iedu_"):
                return api_error("Attachments are not supported for this channel.", code="BAD_REQUEST", status_code=400)
            return api_error("Conversation not found.", code="NOT_FOUND", status_code=404)

        uploaded = request.FILES.get("file")
        if not uploaded:
            return api_error("No file provided.", code="BAD_REQUEST", status_code=400)

        error = _validate_attachment(uploaded)
        if error:
            return api_error(error, code="BAD_REQUEST", status_code=400)

        import os
        from .models import MessageAttachment

        name = os.path.basename(uploaded.name or "file")
        ext = os.path.splitext(name)[1].lower()
        mime = getattr(uploaded, "content_type", "") or "application/octet-stream"
        message_type = "image" if mime.startswith("image/") else "file"

        content = (request.data.get("content") or "").strip() or name
        message = Message.objects.create(
            conversation=conv,
            workspace=conv.workspace,
            sender_type="agent",
            direction="outbound",
            message_type=message_type,
            content=content,
            sent_by=request.user,
            status="sent",
        )
        MessageAttachment.objects.create(
            message=message,
            file=uploaded,
            file_type=message_type,
            file_name=name,
            file_size=uploaded.size,
            mime_type=mime,
        )

        conv.last_message_at = timezone.now()
        conv.last_message_preview = content[:100]
        conv.status = "open"
        conv.unread_count = 0
        conv.save(update_fields=["last_message_at", "last_message_preview", "status", "unread_count"])

        try:
            from .consumers import broadcast_new_message, broadcast_workspace_event
            broadcast_new_message(message)
            broadcast_workspace_event(
                str(conv.workspace_id), "new_message",
                {"conversation_id": str(conv.id), "channel": conv.channel},
            )
        except Exception:
            pass

        return Response(MessageSerializer(message).data, status=201)


class AttachmentDownloadView(APIView):
    """GET /api/conversations/attachments/<id>/ — authenticated download."""
    permission_classes = [IsAuthenticated]

    def get(self, request, attachment_id):
        from .models import MessageAttachment
        from django.http import FileResponse, Http404

        attachment = MessageAttachment.objects.select_related(
            "message__conversation__workspace"
        ).filter(id=attachment_id).first()
        if not attachment:
            raise Http404

        ws_ids = get_user_workspaces(request.user)
        if str(attachment.message.conversation.workspace_id) not in ws_ids:
            raise Http404  # don't leak existence across tenants

        import os
        filename = os.path.basename(attachment.file_name or attachment.file.name)
        return FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.mime_type or "application/octet-stream",
            as_attachment=True,
            filename=filename,
        )


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

    def _iedu_labels(self, request, conversation_id):
        """Return (client, pk, current_label_entries) for an iedu conv."""
        from apps.integrations.iedu.proxy import client_for_user, iedu_pk
        client = client_for_user(request.user)
        if not client:
            return None, None, None
        pk = iedu_pk(conversation_id)
        conv, _ = client.get_messages(pk, limit=1)
        return client, pk, list((conv or {}).get("labels") or [])

    def get(self, request, conversation_id):
        if str(conversation_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import _label_dict
            client, _, labels = self._iedu_labels(request, conversation_id)
            if client is None:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            return Response([_label_dict(l) for l in labels])
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        return Response(LabelSerializer(conv.labels.all(), many=True).data)

    def post(self, request, conversation_id):
        if str(conversation_id).startswith("iedu_"):
            from apps.integrations.iedu.proxy import _label_dict
            client, pk, labels = self._iedu_labels(request, conversation_id)
            if client is None:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            label = Label.objects.filter(
                id=request.data.get("label_id"),
                workspace__members__user=request.user,
            ).first()
            if not label:
                return api_error("Label not found.", code="NOT_FOUND", status_code=404)
            if label.name not in labels:
                labels.append(label.name)
                client.set_labels(pk, labels)
            return Response([_label_dict(l) for l in labels], status=201)
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        label_id = request.data.get("label_id")
        label = Label.objects.filter(id=label_id, workspace=conv.workspace).first()
        if not label:
            return api_error("Label not found.", code="NOT_FOUND", status_code=404)
        ConversationLabel.objects.get_or_create(conversation=conv, label=label)
        from apps.integrations.iedu.actions import push_labels
        push_labels(conv)
        return Response(LabelSerializer(conv.labels.all(), many=True).data, status=201)

    def delete(self, request, conversation_id):
        if str(conversation_id).startswith("iedu_"):
            client, pk, labels = self._iedu_labels(request, conversation_id)
            if client is None:
                return api_error("Not found.", code="NOT_FOUND", status_code=404)
            label = Label.objects.filter(
                id=request.data.get("label_id"),
                workspace__members__user=request.user,
            ).first()
            name = label.name if label else request.data.get("label_id")
            labels = [l for l in labels if l != name]
            client.set_labels(pk, labels)
            return Response(status=204)
        conv = get_conversation_for_user(request.user, conversation_id)
        if not conv:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        label_id = request.data.get("label_id")
        ConversationLabel.objects.filter(conversation=conv, label_id=label_id).delete()
        from apps.integrations.iedu.actions import push_labels
        push_labels(conv)
        return Response(status=204)


class LabelListCreateView(generics.ListCreateAPIView):
    queryset = Label.objects.none()
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Label.objects.filter(workspace_id__in=ws_ids)

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Invalid workspace.")
        serializer.save(workspace_id=ws_id)


class LabelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LabelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
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


class FacebookPagesView(APIView):
    """List all connected Facebook Pages across all Facebook integrations.
    Used by the inbox to build a page filter dropdown."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        ws_ids = get_user_workspaces(request.user)
        from apps.integrations.models import Integration
        pages = []
        seen = set()
        for integration in Integration.objects.filter(
            workspace_id__in=ws_ids,
            integration_type="facebook",
            status="connected",
        ):
            for page in (integration.config or {}).get("connected_pages", []):
                pid = page.get("page_id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    pages.append({
                        "page_id": pid,
                        "page_name": page.get("page_name", ""),
                        "integration_id": str(integration.id),
                    })
        return api_success(data=pages, message="Facebook pages")
