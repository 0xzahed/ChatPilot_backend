from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsWorkspaceMember(BasePermission):
    """User must be a member of the workspace specified in the request."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        ws_id = view.kwargs.get("workspace_id") or request.query_params.get("workspace_id")
        if ws_id:
            return request.user.workspace_memberships.filter(workspace_id=ws_id).exists()
        return True

    def has_object_permission(self, request, view, obj):
        workspace = getattr(obj, "workspace", None)
        if workspace is None:
            return False
        return request.user.workspace_memberships.filter(workspace=workspace).exists()


class IsWorkspaceAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        ws_id = view.kwargs.get("workspace_id") or request.query_params.get("workspace_id")
        if ws_id:
            return request.user.workspace_memberships.filter(
                workspace_id=ws_id, role__in=["owner", "admin"]
            ).exists()
        return True


class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None) or getattr(obj, "created_by", None)
        return owner == request.user


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_platform_admin)
