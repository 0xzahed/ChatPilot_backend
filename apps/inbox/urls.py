from django.urls import path
from .views import (
    ConversationListView, ConversationDetailView, MessageListView,
    SendMessageView, AssignConversationView, CloseConversationView,
    ReopenConversationView, MarkUnreadView, AISuggestView,
    ConversationLabelsView, LabelListCreateView, LabelDetailView,
    TypingIndicatorView, FacebookPagesView,
)

urlpatterns = [
    path("", ConversationListView.as_view(), name="conversation-list"),
    path("facebook-pages/", FacebookPagesView.as_view(), name="facebook-pages"),
    path("<uuid:conversation_id>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("<uuid:conversation_id>/messages/", MessageListView.as_view(), name="message-list"),
    path("<uuid:conversation_id>/messages/send/", SendMessageView.as_view(), name="send-message"),
    path("<uuid:conversation_id>/assign/", AssignConversationView.as_view(), name="assign"),
    path("<uuid:conversation_id>/close/", CloseConversationView.as_view(), name="close"),
    path("<uuid:conversation_id>/reopen/", ReopenConversationView.as_view(), name="reopen"),
    path("<uuid:conversation_id>/mark-unread/", MarkUnreadView.as_view(), name="mark-unread"),
    path("<uuid:conversation_id>/ai-suggest/", AISuggestView.as_view(), name="ai-suggest"),
    path("<uuid:conversation_id>/labels/", ConversationLabelsView.as_view(), name="conversation-labels"),
    path("<uuid:conversation_id>/typing/", TypingIndicatorView.as_view(), name="typing"),
    path("labels/", LabelListCreateView.as_view(), name="label-list"),
    path("labels/<uuid:pk>/", LabelDetailView.as_view(), name="label-detail"),
]
