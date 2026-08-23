from django.urls import path
from .views import (
    AISettingsView, AIInstructionsView, AIEventListView, AIUsageView, AITestView,
)

urlpatterns = [
    path("<uuid:workspace_id>/settings/", AISettingsView.as_view(), name="ai-settings"),
    path("<uuid:workspace_id>/instructions/", AIInstructionsView.as_view(), name="ai-instructions"),
    path("events/", AIEventListView.as_view(), name="ai-events"),
    path("<uuid:workspace_id>/usage/", AIUsageView.as_view(), name="ai-usage"),
    path("<uuid:workspace_id>/test/", AITestView.as_view(), name="ai-test"),
]
