from django.urls import path
from .views import (
    WorkspaceListView, WorkspaceDetailView,
    WorkspaceMembersView, WorkspaceSettingsView,
)

urlpatterns = [
    path("", WorkspaceListView.as_view(), name="workspace-list"),
    path("<uuid:workspace_id>/", WorkspaceDetailView.as_view(), name="workspace-detail"),
    path("<uuid:workspace_id>/members/", WorkspaceMembersView.as_view(), name="workspace-members"),
    path("<uuid:workspace_id>/settings/", WorkspaceSettingsView.as_view(), name="workspace-settings"),
]
