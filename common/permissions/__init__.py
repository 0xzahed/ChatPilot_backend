from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied


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


# ─── Helpers (used by views that don't use object-level permissions) ───

def is_workspace_admin(user, workspace_id) -> bool:
    """Return True if the user is an owner/admin of the given workspace."""
    if not user or not user.is_authenticated or not workspace_id:
        return False
    return user.workspace_memberships.filter(
        workspace_id=workspace_id, role__in=["owner", "admin"]
    ).exists()


def require_workspace_admin(user, workspace_id):
    """Raise PermissionDenied unless the user is an admin/owner of the workspace."""
    if not is_workspace_admin(user, workspace_id):
        raise PermissionDenied("You must be an admin or owner of this workspace.")


# ─── Role-based write access ────────────────────────────────────────────
ROLE_RANK = {"viewer": 0, "agent": 1, "manager": 2, "admin": 3, "owner": 4}

# Minimum role required for unsafe methods (POST/PUT/PATCH/DELETE), by app.
# Reading is allowed for every workspace member (viewers included).
APP_WRITE_ROLE = {
    "inbox": "agent",
    "customers": "agent",
    "orders": "agent",
    "complaints": "agent",
    "products": "agent",
    "labels": "manager",
    "automation": "manager",
    "ai": "manager",
    "integrations": "admin",
    "workspaces": "admin",
    "billing": "admin",
    "webhooks": "admin",
}


def _resolve_workspace_id(request, view):
    """Best-effort workspace id for the request, or None if it can't be told."""
    ws_id = view.kwargs.get("workspace_id")
    if not ws_id:
        data = getattr(request, "data", None)
        if hasattr(data, "get"):
            ws_id = data.get("workspace_id") or data.get("workspace")
    if not ws_id:
        ws_id = request.query_params.get("workspace_id")
    if not ws_id and view.kwargs.get("conversation_id"):
        from apps.inbox.models import Conversation
        try:
            ws_id = Conversation.objects.filter(
                id=view.kwargs["conversation_id"]
            ).values_list("workspace_id", flat=True).first()
        except Exception:
            ws_id = None
    if not ws_id:
        return None
    return str(ws_id)


class WorkspaceRolePermission(BasePermission):
    """Enforce the workspace role hierarchy on write requests.

    viewer < agent < manager < admin < owner. Safe methods are open to any
    authenticated user (queryset filters already scope data to workspaces the
    user belongs to). A view may set ``min_write_role`` (a role name, or None
    to opt out); otherwise the app default in ``APP_WRITE_ROLE`` applies.
    """

    message = "Your role in this workspace does not allow this action."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, "min_write_role", "__default__")
        if required == "__default__":
            app = view.__class__.__module__.split(".")[1:2]
            required = APP_WRITE_ROLE.get(app[0]) if app else None
        if not required:
            return True
        need = ROLE_RANK[required]
        memberships = user.workspace_memberships.all()
        ws_id = _resolve_workspace_id(request, view)
        if ws_id:
            try:
                memberships = memberships.filter(workspace_id=ws_id)
            except Exception:
                return True  # malformed id: let the view return its own 400/404
            if not memberships.exists():
                return True  # not a member: the view's own scoping returns 404
        roles = memberships.values_list("role", flat=True)
        return any(ROLE_RANK.get(r, 0) >= need for r in roles) or not roles


def resolve_create_workspace_id(request):
    """Workspace a new object should belong to, for create endpoints.

    Uses ``workspace_id`` from the body when it is one of the user's workspaces;
    refuses a workspace they don't belong to (instead of silently filing the
    object under a different one); with no ``workspace_id`` it is only
    unambiguous when the user has exactly one workspace.
    """
    from rest_framework.exceptions import ValidationError
    ws_ids = [str(p) for p in request.user.workspace_memberships.values_list("workspace_id", flat=True)]
    ws_id = request.data.get("workspace_id")
    if ws_id:
        if str(ws_id) not in ws_ids:
            raise PermissionDenied("Invalid workspace.")
        return str(ws_id)
    if len(ws_ids) == 1:
        return ws_ids[0]
    raise ValidationError({"workspace_id": "This field is required."})
