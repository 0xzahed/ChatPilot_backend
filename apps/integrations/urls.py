from django.urls import path
from .views import (
    IntegrationListView, IntegrationDetailView, IntegrationConnectView,
    IntegrationCallbackView, IntegrationDisconnectView,
    WebhookEventListView, WebhookReplayView, SyncLogListView, IntegrationSyncView,
)

urlpatterns = [
    path("", IntegrationListView.as_view(), name="integration-list"),
    path("<uuid:pk>/", IntegrationDetailView.as_view(), name="integration-detail"),
    path("<uuid:pk>/disconnect/", IntegrationDisconnectView.as_view(), name="integration-disconnect"),
    path("<uuid:pk>/sync/", IntegrationSyncView.as_view(), name="integration-sync"),
    path("connect/<str:integration_type>/", IntegrationConnectView.as_view(), name="integration-connect"),
    path("callback/<str:integration_type>/", IntegrationCallbackView.as_view(), name="integration-callback"),
    path("webhooks/", WebhookEventListView.as_view(), name="webhook-event-list"),
    path("webhooks/<uuid:event_id>/replay/", WebhookReplayView.as_view(), name="webhook-replay"),
    path("sync-logs/", SyncLogListView.as_view(), name="sync-log-list"),
]
