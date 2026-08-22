from django.urls import path
from .views import (
    AISettingsView, AIInstructionsView, AIEventListView, AIUsageView,
)

urlpatterns = [
    path("<uuid:workspace_id>/settings/", AISettingsView.as_view(), name="ai-settings"),
    path("<uuid:workspace_id>/instructions/", AIInstructionsView.as_view(), name="ai-instructions"),
    path("events/", AIEventListView.as_view(), name="ai-events"),
    path("<uuid:workspace_id>/usage/", AIUsageView.as_view(), name="ai-usage"),
]
