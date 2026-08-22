from django.urls import path
from .consumers import ConversationConsumer, WorkspaceConsumer

websocket_urlpatterns = [
    path("ws/conversations/<uuid:conversation_id>/", ConversationConsumer.as_asgi()),
    path("ws/workspaces/<uuid:workspace_id>/", WorkspaceConsumer.as_asgi()),
]
