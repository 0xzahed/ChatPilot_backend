import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def _broadcast(event_type, conversation, data):
    """Helper to broadcast events to the conversation's group."""
    if channel_layer is None:
        return
    group = f"conversation_{conversation.id}"
    async_to_sync(channel_layer.group_send)(
        group,
        {"type": "broadcast.message", "event": event_type, "data": data},
    )


def broadcast_new_message(message):
    from .serializers import MessageSerializer
    from rest_framework.test import APIRequestFactory
    _broadcast("new_message", message.conversation, {
        "message": MessageSerializer(message).data,
    })


def broadcast_conversation_update(conversation):
    from .serializers import ConversationListSerializer
    _broadcast("conversation_updated", conversation, {
        "conversation": ConversationListSerializer(conversation).data,
    })


def broadcast_typing(conversation, user, is_typing):
    _broadcast("typing", conversation, {
        "user_id": str(user.id),
        "user_name": user.get_full_name() or user.username,
        "is_typing": is_typing,
    })


def broadcast_ai_processing(conversation):
    _broadcast("ai_processing", conversation, {"conversation_id": str(conversation.id)})


def broadcast_ai_completed(conversation, suggestion):
    _broadcast("ai_completed", conversation, {"suggestion": suggestion})


@database_sync_to_async
def _user_can_access_conversation(user, conversation_id):
    """Check if user is a member of the workspace that owns the conversation.

    Returns False for non-existent conversations as well (no information leak).
    """
    from apps.inbox.models import Conversation
    from apps.workspaces.models import WorkspaceMembership

    try:
        conversation = Conversation.objects.select_related("workspace").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return False

    return WorkspaceMembership.objects.filter(
        workspace=conversation.workspace,
        user=user,
    ).exists()


@database_sync_to_async
def _user_is_workspace_member(user, workspace_id):
    """Check if user is a member of the specified workspace."""
    from apps.workspaces.models import WorkspaceMembership

    return WorkspaceMembership.objects.filter(
        workspace_id=workspace_id,
        user=user,
    ).exists()


class ConversationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"conversation_{self.conversation_id}"

        # Auth check — user must be authenticated
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        # Authorization check — user must be a member of the conversation's workspace
        has_access = await _user_can_access_conversation(user, self.conversation_id)
        if not has_access:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                # Channel layer may be down (Redis restart) — a dropped
                # group membership is harmless; the channel is closing anyway.
                pass

    async def broadcast_message(self, event):
        """Handler for broadcast.message events from group_send."""
        await self.send_json({
            "event": event["event"],
            "data": event["data"],
        })


class WorkspaceConsumer(AsyncJsonWebsocketConsumer):
    """Broadcasts workspace-level events (new conversation, notifications)."""

    async def connect(self):
        self.workspace_id = self.scope["url_route"]["kwargs"]["workspace_id"]
        self.group_name = f"workspace_{self.workspace_id}"

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        # Authorization check — user must be a member of the workspace
        is_member = await _user_is_workspace_member(user, self.workspace_id)
        if not is_member:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                # Channel layer may be down (Redis restart) — harmless.
                pass

    async def broadcast_message(self, event):
        await self.send_json({
            "event": event["event"],
            "data": event["data"],
        })


def broadcast_workspace_event(workspace_id, event_type, data):
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"workspace_{workspace_id}",
        {"type": "broadcast.message", "event": event_type, "data": data},
    )
