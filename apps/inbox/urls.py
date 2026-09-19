from django.urls import path
from .views import (
    ConversationListView, ConversationDetailView, MessageListView,
    SendMessageView, AssignConversationView, CloseConversationView,
    ReopenConversationView, MarkUnreadView, AISuggestView,
    ConversationLabelsView, LabelListCreateView, LabelDetailView,
    TypingIndicatorView, FacebookPagesView,
    ConversationAttachmentUploadView, AttachmentDownloadView,
)

urlpatterns = [
    path("", ConversationListView.as_view(), name="conversation-list"),
    path("facebook-pages/", FacebookPagesView.as_view(), name="facebook-pages"),
    path("attachments/<uuid:attachment_id>/", AttachmentDownloadView.as_view(), name="attachment-download"),
    path("<str:conversation_id>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("<str:conversation_id>/messages/", MessageListView.as_view(), name="message-list"),
    path("<str:conversation_id>/messages/send/", SendMessageView.as_view(), name="send-message"),
    path("<str:conversation_id>/assign/", AssignConversationView.as_view(), name="assign"),
    path("<str:conversation_id>/close/", CloseConversationView.as_view(), name="close"),
    path("<str:conversation_id>/reopen/", ReopenConversationView.as_view(), name="reopen"),
    path("<str:conversation_id>/mark-unread/", MarkUnreadView.as_view(), name="mark-unread"),
    path("<str:conversation_id>/ai-suggest/", AISuggestView.as_view(), name="ai-suggest"),
    path("<str:conversation_id>/labels/", ConversationLabelsView.as_view(), name="conversation-labels"),
    path("<str:conversation_id>/typing/", TypingIndicatorView.as_view(), name="typing"),
    path("<str:conversation_id>/attachments/", ConversationAttachmentUploadView.as_view(), name="attachment-upload"),
    path("labels/", LabelListCreateView.as_view(), name="label-list"),
    path("labels/<uuid:pk>/", LabelDetailView.as_view(), name="label-detail"),
]
