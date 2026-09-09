from django.urls import path
from .views import (
    IntegrationListView, IntegrationDetailView, IntegrationConnectView,
    IntegrationCallbackView, IntegrationCompleteView, IntegrationDisconnectView,
    WebhookEventListView, WebhookReplayView, SyncLogListView, IntegrationSyncView,
    WhatsAppSetupView, IntegrationSelectPagesView,
)

urlpatterns = [
    path("", IntegrationListView.as_view(), name="integration-list"),
    path("<uuid:pk>/", IntegrationDetailView.as_view(), name="integration-detail"),
    path("<uuid:pk>/disconnect/", IntegrationDisconnectView.as_view(), name="integration-disconnect"),
    path("<uuid:pk>/sync/", IntegrationSyncView.as_view(), name="integration-sync"),
    path("<uuid:pk>/select-pages/", IntegrationSelectPagesView.as_view(), name="integration-select-pages"),
    path("connect/<str:integration_type>/", IntegrationConnectView.as_view(), name="integration-connect"),
    path("callback/<str:integration_type>/", IntegrationCallbackView.as_view(), name="integration-callback"),
    path("complete/<str:integration_type>/", IntegrationCompleteView.as_view(), name="integration-complete"),
    path("whatsapp/setup/", WhatsAppSetupView.as_view(), name="whatsapp-setup"),
    path("webhooks/", WebhookEventListView.as_view(), name="webhook-event-list"),
    path("webhooks/<uuid:event_id>/replay/", WebhookReplayView.as_view(), name="webhook-replay"),
    path("sync-logs/", SyncLogListView.as_view(), name="sync-log-list"),
]
