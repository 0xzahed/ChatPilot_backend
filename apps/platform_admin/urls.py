from django.urls import path
from .views import (
    PlatformStatsView,
    AdminUserListView, AdminUserDetailView,
    AdminWorkspaceListView, AdminWorkspaceDetailView,
    AdminAuditLogListView,
)

urlpatterns = [
    path("stats/", PlatformStatsView.as_view(), name="platform-stats"),
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<uuid:pk>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("workspaces/", AdminWorkspaceListView.as_view(), name="admin-workspace-list"),
    path("workspaces/<uuid:pk>/", AdminWorkspaceDetailView.as_view(), name="admin-workspace-detail"),
    path("audit/", AdminAuditLogListView.as_view(), name="admin-audit-list"),
]
