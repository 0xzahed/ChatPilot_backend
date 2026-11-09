import uuid
import pytest
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.customers.models import Customer
from apps.inbox.models import Conversation
from apps.workspaces.models import Workspace, WorkspaceMembership

ROLES = ["owner", "admin", "manager", "agent", "viewer"]


@pytest.fixture
def env(db):
    def mk(name, **kw):
        return User.objects.create_user(
            email=f"{name}@t.local", username=f"{name}{uuid.uuid4().hex[:5]}", password="pw-" + uuid.uuid4().hex, **kw
        )

    users = {r: mk(r) for r in ROLES}
    ws = Workspace.objects.create(name="W", slug="w-" + uuid.uuid4().hex[:6], owner=users["owner"])
    for r, u in users.items():
        WorkspaceMembership.objects.create(workspace=ws, user=u, role=r)
    conv = Conversation.objects.create(
        workspace=ws, customer=Customer.objects.create(workspace=ws, name="C"), channel="webchat"
    )
    return {"users": users, "ws": ws, "conv": conv, "mk": mk}


def call(user, method, url, data=None):
    c = APIClient()
    c.force_authenticate(user)
    return getattr(c, method)(url, data or {}, format="json").status_code


def test_viewer_cannot_reply_but_agent_can(env):
    url = f"/api/conversations/{env['conv'].id}/messages/send/"
    assert call(env["users"]["viewer"], "post", url, {"content": "hi"}) == 403
    assert call(env["users"]["agent"], "post", url, {"content": "hi"}) == 201


def test_everyone_can_read(env):
    for u in env["users"].values():
        assert call(u, "get", f"/api/conversations/{env['conv'].id}/") == 200


@pytest.mark.parametrize("role,expected", [("owner", 201), ("admin", 201), ("manager", 201), ("agent", 403), ("viewer", 403)])
def test_label_create_needs_manager(env, role, expected):
    body = {"name": "L" + uuid.uuid4().hex[:6], "color": "#fff", "workspace_id": str(env["ws"].id)}
    assert call(env["users"][role], "post", "/api/labels/", body) == expected


@pytest.mark.parametrize("role,expected", [("owner", 200), ("admin", 200), ("manager", 403), ("agent", 403), ("viewer", 403)])
def test_workspace_settings_and_rename_need_admin(env, role, expected):
    ws = env["ws"].id
    assert call(env["users"][role], "patch", f"/api/workspaces/{ws}/settings/", {"business_name": "X"}) == expected
    assert call(env["users"][role], "patch", f"/api/workspaces/{ws}/", {"name": "New"}) == expected


def test_outsider_blocked_from_other_workspace(env):
    out = env["mk"]("outsider")
    assert call(out, "get", f"/api/conversations/{env['conv'].id}/") == 404
    assert call(out, "patch", f"/api/workspaces/{env['ws'].id}/", {"name": "x"}) == 404


def test_any_user_can_still_create_their_own_workspace(env):
    solo = env["mk"]("solo")
    assert call(solo, "post", "/api/workspaces/", {"name": "Mine", "slug": "mine-" + uuid.uuid4().hex[:6]}) in (200, 201)


def test_platform_admin_api_is_super_admin_only(env):
    sa = env["mk"]("sa", is_platform_admin=True)
    assert call(sa, "get", "/api/admin/stats/") == 200
    assert call(env["users"]["owner"], "get", "/api/admin/stats/") == 403


def test_oauth_complete_with_bad_state_is_400_not_500(env):
    assert call(env["users"]["owner"], "post", "/api/integrations/complete/facebook/", {"code": "x", "state": ""}) == 400
    assert call(env["users"]["owner"], "post", "/api/integrations/complete/facebook/", {"code": "x", "state": "nope"}) == 400


def test_label_create_without_workspace_is_400_for_multi_or_none(env):
    out = env["mk"]("nolabel")
    assert call(out, "post", "/api/labels/", {"name": "z", "color": "#fff"}) in (400, 403)


def test_workspace_payload_includes_my_role(env):
    c = APIClient(); c.force_authenticate(env["users"]["manager"])
    r = c.get("/api/workspaces/")
    items = r.json()["data"]
    assert any(w.get("role") == "manager" for w in items)


def test_bad_conversation_id_is_404_not_500(env):
    for tail in ["", "messages/", "close/"]:
        m = "get" if tail in ("", "messages/") else "post"
        assert call(env["users"]["owner"], m, f"/api/conversations/not-a-uuid/{tail}") == 404


@pytest.mark.parametrize("url,body", [
    ("/api/customers/", {"name": "x"}),
    ("/api/products/", {"name": "x", "price": "1.00"}),
    ("/api/automation/rules/", {"name": "x"}),
])
def test_create_without_workspace_never_500s_or_misfiles(env, url, body):
    nomember = env["mk"]("nm")
    assert call(nomember, "post", url, body) in (400, 403)
    # naming a workspace you are not in is refused, not silently re-filed
    assert call(env["users"]["owner"], "post", url, {**body, "workspace_id": str(uuid.uuid4())}) == 403
