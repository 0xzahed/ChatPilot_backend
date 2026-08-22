from django.urls import path
from .views import WebhookEventListView, WebhookEventDetailView, WebhookReplayView

urlpatterns = [
    path("", WebhookEventListView.as_view(), name="webhook-event-list"),
    path("<uuid:pk>/", WebhookEventDetailView.as_view(), name="webhook-event-detail"),
    path("<uuid:event_id>/replay/", WebhookReplayView.as_view(), name="webhook-replay"),
]
