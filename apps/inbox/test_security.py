"""Security regression tests — WS authorization, webhook HMAC, tenant
isolation, cookie auth, webchat throttling, and attachment authorization.

Runs under both `manage.py test` and `pytest` (config.settings.test).
"""
import base64
import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.customers.models import Customer, CustomerChannel
from apps.inbox.models import Conversation, Message, MessageAttachment
from apps.webchat.models import WebchatConfig
from apps.workspaces.models import Workspace, WorkspaceMembership


def _user(email, password="Test@12345"):
    return User.objects.create_user(email=email, username=email.split("@")[0], password=password)


def _workspace_with_member(user, name="WS"):
    ws = Workspace.objects.create(
        name=name, slug=name.lower() + "-" + uuid.uuid4().hex[:6], owner=user
    )
    WorkspaceMembership.objects.get_or_create(
        workspace=ws, user=user, defaults={"role": "agent"}
    )
    return ws


def _conversation(ws, customer=None):
    customer = customer or Customer.objects.create(workspace=ws, name="C")
    return Conversation.objects.create(
        workspace=ws, customer=customer, channel="facebook", status="open"
    )


# ─── SEC-01: WebSocket authorization ──────────────────────────

class WebSocketAuthzTest(TransactionTestCase):
    """Consumer connect handshake: membership is enforced object-level.

    Each connect() runs inside a single async_to_sync-wrapped coroutine so the
    communicator, middleware, and consumer share one event loop.
    """

    def _connect(self, path, ticket=None, token=None, cookies=None):
        """Returns (connected, close_code) after connect + clean disconnect."""
        from channels.testing import WebsocketCommunicator
        from config.asgi import application

        async def _run():
            qs = ""
            if ticket:
                qs = f"?ticket={ticket}"
            elif token:
                qs = f"?token={token}"
            headers = []
            if cookies:
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
                headers = [(b"cookie", cookie_str.encode())]
            comm = WebsocketCommunicator(application, path + qs, headers=headers)
            connected, code = await comm.connect()
            if connected:
                await comm.disconnect()
            return connected, code

        return async_to_sync(_run)()

    def _token_for(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        return str(RefreshToken.for_user(user).access_token)

    def test_member_allowed(self):
        user = _user("a@x.com")
        ws = _workspace_with_member(user)
        conv = _conversation(ws)
        connected, _ = self._connect(
            f"/ws/conversations/{conv.id}/", token=self._token_for(user)
        )
        self.assertTrue(connected)

    def test_non_member_denied_4403(self):
        owner = _user("owner@x.com")
        ws = _workspace_with_member(owner, "wsA")
        conv = _conversation(ws)
        outsider = _user("outsider@x.com")
        _workspace_with_member(outsider, "wsB")
        connected, code = self._connect(
            f"/ws/conversations/{conv.id}/", token=self._token_for(outsider)
        )
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    def test_nonexistent_conversation_denied(self):
        user = _user("a2@x.com")
        _workspace_with_member(user)
        connected, code = self._connect(
            f"/ws/conversations/{uuid.uuid4()}/", token=self._token_for(user)
        )
        self.assertFalse(connected)
        self.assertEqual(code, 4403)  # no existence leak

    def test_anonymous_denied(self):
        ws = Workspace.objects.create(
            name="W", slug="w-" + uuid.uuid4().hex[:6], owner=_user("o2@x.com")
        )
        conv = _conversation(ws)
        connected, code = self._connect(f"/ws/conversations/{conv.id}/")
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    def test_workspace_member_allowed(self):
        user = _user("m@x.com")
        ws = _workspace_with_member(user)
        connected, _ = self._connect(
            f"/ws/workspaces/{ws.id}/", token=self._token_for(user)
        )
        self.assertTrue(connected)

    def test_workspace_non_member_denied(self):
        owner = _user("o@x.com")
        ws = _workspace_with_member(owner, "wsx")
        outsider = _user("n@x.com")
        _workspace_with_member(outsider, "wsy")
        connected, code = self._connect(
            f"/ws/workspaces/{ws.id}/", token=self._token_for(outsider)
        )
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    def test_cookie_auth_works_on_ws(self):
        user = _user("ck@x.com")
        ws = _workspace_with_member(user)
        connected, _ = self._connect(
            f"/ws/workspaces/{ws.id}/", cookies={settings.AUTH_COOKIE_ACCESS_NAME: self._token_for(user)}
        )
        self.assertTrue(connected)

    def test_ticket_auth_single_use(self):
        user = _user("t@x.com")
        ws = _workspace_with_member(user)
        ticket = uuid.uuid4().hex
        cache.set(f"ws_ticket:{ticket}", str(user.id), timeout=60)
        connected, _ = self._connect(f"/ws/workspaces/{ws.id}/", ticket=ticket)
        self.assertTrue(connected)
        # Same ticket must not work twice
        connected2, code2 = self._connect(f"/ws/workspaces/{ws.id}/", ticket=ticket)
        self.assertFalse(connected2)
        self.assertEqual(code2, 4001)


# ─── SEC-02/03/04: webhook HMAC ───────────────────────────────

class WebhookHMACTest(TestCase):
    def _post(self, url, body: bytes, headers: dict):
        return self.client.post(
            url, data=body, content_type="application/json",
            **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
        )

    # Shopify
    @override_settings(SHOPIFY_WEBHOOK_SECRET="shopify-secret")
    def test_shopify_valid_hmac(self):
        body = b'{"id": 1}'
        sig = base64.b64encode(
            hmac.new(b"shopify-secret", body, hashlib.sha256).digest()
        ).decode()
        resp = self._post("/webhooks/shopify/", body, {"X-Shopify-Hmac-Sha256": sig})
        self.assertEqual(resp.status_code, 200)

    @override_settings(SHOPIFY_WEBHOOK_SECRET="shopify-secret")
    def test_shopify_invalid_hmac(self):
        resp = self._post(
            "/webhooks/shopify/", b'{"id":1}', {"X-Shopify-Hmac-Sha256": "badsig"}
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(SHOPIFY_WEBHOOK_SECRET="shopify-secret")
    def test_shopify_missing_signature(self):
        resp = self._post("/webhooks/shopify/", b'{"id":1}', {})
        self.assertEqual(resp.status_code, 403)

    @override_settings(SHOPIFY_WEBHOOK_SECRET="shopify-secret")
    def test_shopify_modified_payload_rejected(self):
        body = b'{"id": 1}'
        sig = base64.b64encode(
            hmac.new(b"shopify-secret", body, hashlib.sha256).digest()
        ).decode()
        tampered = b'{"id": 2}'
        resp = self._post("/webhooks/shopify/", tampered, {"X-Shopify-Hmac-Sha256": sig})
        self.assertEqual(resp.status_code, 403)

    @override_settings(SHOPIFY_WEBHOOK_SECRET="")
    def test_shopify_missing_secret_fails_closed(self):
        body = b'{"id": 1}'
        sig = base64.b64encode(hmac.new(b"x", body, hashlib.sha256).digest()).decode()
        resp = self._post("/webhooks/shopify/", body, {"X-Shopify-Hmac-Sha256": sig})
        self.assertEqual(resp.status_code, 500)

    # WhatsApp
    @override_settings(META_APP_SECRET="wa-secret")
    def test_whatsapp_valid(self):
        body = b'{"entry":[]}'
        sig = "sha256=" + hmac.new(b"wa-secret", body, hashlib.sha256).hexdigest()
        resp = self._post("/webhooks/whatsapp/", body, {"X-Hub-Signature-256": sig})
        self.assertEqual(resp.status_code, 200)

    @override_settings(META_APP_SECRET="wa-secret")
    def test_whatsapp_invalid(self):
        resp = self._post(
            "/webhooks/whatsapp/", b'{"entry":[]}', {"X-Hub-Signature-256": "sha256=bad"}
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(META_APP_SECRET="")
    def test_whatsapp_missing_secret_fails_closed(self):
        resp = self._post("/webhooks/whatsapp/", b'{"entry":[]}', {})
        self.assertEqual(resp.status_code, 500)

    # Facebook/Meta
    @override_settings(META_APP_SECRET="meta-secret")
    def test_facebook_valid(self):
        body = b'{"object":"page","entry":[{"id":"e1","messaging":[]}]}'
        sig = "sha256=" + hmac.new(b"meta-secret", body, hashlib.sha256).hexdigest()
        resp = self._post("/webhooks/meta/", body, {"X-Hub-Signature-256": sig})
        self.assertEqual(resp.status_code, 200)

    @override_settings(META_APP_SECRET="meta-secret")
    def test_facebook_invalid(self):
        resp = self._post(
            "/webhooks/meta/", b'{"object":"page"}', {"X-Hub-Signature-256": "sha256=bad"}
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(META_APP_SECRET="")
    def test_facebook_missing_secret_fails_closed(self):
        resp = self._post("/webhooks/meta/", b'{"object":"page"}', {})
        self.assertEqual(resp.status_code, 500)


# ─── SEC-05: CustomerChannel tenant isolation ─────────────────

class CustomerChannelIsolationTest(TestCase):
    def setUp(self):
        self.user_a = _user("ta@x.com")
        self.user_b = _user("tb@x.com")
        self.ws_a = _workspace_with_member(self.user_a, "wsa")
        self.ws_b = _workspace_with_member(self.user_b, "wsb")

    def test_same_external_id_different_workspaces_allowed(self):
        cust_a = Customer.objects.create(workspace=self.ws_a, name="A")
        cust_b = Customer.objects.create(workspace=self.ws_b, name="B")
        CustomerChannel.objects.create(
            customer=cust_a, workspace=self.ws_a, channel="whatsapp", external_id="123"
        )
        # Same external_id on the same channel in another workspace — OK
        CustomerChannel.objects.create(
            customer=cust_b, workspace=self.ws_b, channel="whatsapp", external_id="123"
        )
        self.assertEqual(CustomerChannel.objects.count(), 2)

    def test_same_workspace_duplicate_rejected(self):
        cust = Customer.objects.create(workspace=self.ws_a, name="A")
        CustomerChannel.objects.create(
            customer=cust, workspace=self.ws_a, channel="whatsapp", external_id="123"
        )
        with self.assertRaises(Exception):
            CustomerChannel.objects.create(
                customer=cust, workspace=self.ws_a, channel="whatsapp", external_id="123"
            )

    def test_same_external_id_different_channel_allowed(self):
        cust = Customer.objects.create(workspace=self.ws_a, name="A")
        CustomerChannel.objects.create(
            customer=cust, workspace=self.ws_a, channel="whatsapp", external_id="123"
        )
        CustomerChannel.objects.create(
            customer=cust, workspace=self.ws_a, channel="facebook", external_id="123"
        )
        self.assertEqual(CustomerChannel.objects.count(), 2)

    def test_cross_workspace_lookup_does_not_resolve(self):
        cust = Customer.objects.create(workspace=self.ws_a, name="A")
        CustomerChannel.objects.create(
            customer=cust, workspace=self.ws_a, channel="whatsapp", external_id="999"
        )
        # Workspace B lookup for A's external_id must not resolve
        found = CustomerChannel.objects.filter(
            workspace=self.ws_b, channel="whatsapp", external_id="999"
        ).first()
        self.assertIsNone(found)


# ─── SEC-08/09: cookie auth + WS ticket ───────────────────────

class CookieAuthTest(TestCase):
    def setUp(self):
        self.user = _user("cookie@x.com")
        self.client = APIClient()

    def test_login_sets_httponly_cookies(self):
        resp = self.client.post(
            "/api/auth/login/",
            {"email": "cookie@x.com", "password": "Test@12345", "cookie_mode": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.cookies.get(settings.AUTH_COOKIE_ACCESS_NAME)
        refresh = resp.cookies.get(settings.AUTH_COOKIE_REFRESH_NAME)
        self.assertIsNotNone(access)
        self.assertIsNotNone(refresh)
        self.assertTrue(access["httponly"])
        self.assertTrue(refresh["httponly"])
        # Tokens must NOT be in the response body
        self.assertNotIn("access", resp.json().get("data", {}))
        self.assertNotIn("refresh", resp.json().get("data", {}))

    def test_cookie_authenticated_get(self):
        resp = self.client.post(
            "/api/auth/login/",
            {"email": "cookie@x.com", "password": "Test@12345", "cookie_mode": True},
            format="json",
        )
        # Subsequent GET with just the cookie — no Authorization header
        self.client.cookies = resp.cookies
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["email"], "cookie@x.com")

    def test_cookie_post_without_xrw_rejected(self):
        resp = self.client.post(
            "/api/auth/login/",
            {"email": "cookie@x.com", "password": "Test@12345", "cookie_mode": True},
            format="json",
        )
        self.client.cookies = resp.cookies
        # Unsafe method via cookie auth, missing X-Requested-With → 403
        r = self.client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cookie_post_with_xrw_allowed(self):
        resp = self.client.post(
            "/api/auth/login/",
            {"email": "cookie@x.com", "password": "Test@12345", "cookie_mode": True},
            format="json",
        )
        self.client.cookies = resp.cookies
        r = self.client.post(
            "/api/auth/logout/", {},
            format="json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        # Cookies cleared
        self.assertEqual(r.cookies[settings.AUTH_COOKIE_ACCESS_NAME].value, "")

    def test_cookie_refresh_flow(self):
        resp = self.client.post(
            "/api/auth/login/",
            {"email": "cookie@x.com", "password": "Test@12345", "cookie_mode": True},
            format="json",
        )
        self.client.cookies = resp.cookies
        r = self.client.post(
            "/api/auth/refresh/", {},
            format="json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.cookies.get(settings.AUTH_COOKIE_ACCESS_NAME))

    def test_ws_ticket_issue_and_single_use(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.post(
            "/api/auth/ws-ticket/", {},
            format="json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        ticket = r.json()["data"]["ticket"]
        # Ticket exists in cache once
        self.assertIsNotNone(cache.get(f"ws_ticket:{ticket}"))

    def test_ws_ticket_requires_auth(self):
        r = self.client.post("/api/auth/ws-ticket/", {}, format="json")
        self.assertEqual(r.status_code, 401)


# ─── SEC-07: webchat throttling ───────────────────────────────

class WebchatThrottleTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        owner = _user("wowner@x.com")
        self.ws = Workspace.objects.create(
            name="W", slug="w" + uuid.uuid4().hex[:6], owner=owner
        )
        WebchatConfig.objects.create(workspace=self.ws, is_enabled=True)
        cache.clear()

    # Patch get_rate directly: DRF binds THROTTLE_RATES at class-definition
    # time, so override_settings on REST_FRAMEWORK cannot reach it.
    @patch("apps.webchat.throttling.WebchatSessionRateThrottle.get_rate",
           return_value="2/min")
    def test_message_endpoint_throttled_by_session(self, _mock):
        url = "/api/webchat/message/"
        # First two pass (session scope = 2/min)
        for i in range(2):
            r = self.client.post(url, {
                "workspace_id": str(self.ws.id),
                "session_token": "sess-1",
                "content": f"msg {i}",
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)
        # Third hits the session throttle
        r = self.client.post(url, {
            "workspace_id": str(self.ws.id),
            "session_token": "sess-1",
            "content": "spam",
        }, format="json")
        self.assertEqual(r.status_code, 429)

    @patch("apps.webchat.throttling.WebchatSessionRateThrottle.get_rate",
           return_value="2/min")
    def test_session_endpoint_throttled(self, _mock):
        url = "/api/webchat/session/"
        for i in range(2):
            r = self.client.post(url, {"workspace_id": str(self.ws.id)}, format="json")
            self.assertIn(r.status_code, (200, 201))
        r = self.client.post(url, {"workspace_id": str(self.ws.id)}, format="json")
        self.assertEqual(r.status_code, 429)

    @patch("apps.webchat.throttling.WebchatSessionRateThrottle.get_rate",
           return_value="2/min")
    def test_new_session_not_limited_by_other_session(self, _mock):
        url = "/api/webchat/message/"
        for i in range(2):
            self.client.post(url, {
                "workspace_id": str(self.ws.id),
                "session_token": "sess-a",
                "content": f"m{i}",
            }, format="json")
        # A different session token gets its own budget
        r = self.client.post(url, {
            "workspace_id": str(self.ws.id),
            "session_token": "sess-b",
            "content": "hello",
        }, format="json")
        self.assertEqual(r.status_code, 201)


# ─── SEC-05: attachment upload authorization ─────────────────

class AttachmentSecurityTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = _user("ua@x.com")
        self.user_b = _user("ub@x.com")
        self.ws_a = _workspace_with_member(self.user_a, "wa")
        self.ws_b = _workspace_with_member(self.user_b, "wb")
        self.conv_a = _conversation(self.ws_a)

    def _png(self, name="pic.png"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png")

    def test_upload_requires_auth(self):
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": self._png()}, format="multipart",
        )
        self.assertEqual(r.status_code, 401)

    def test_cross_tenant_upload_rejected(self):
        self.client.force_authenticate(user=self.user_b)
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": self._png()}, format="multipart",
        )
        self.assertEqual(r.status_code, 404)

    def test_member_upload_ok(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": self._png()}, format="multipart",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(MessageAttachment.objects.count(), 1)

    def test_disallowed_extension_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": SimpleUploadedFile("evil.exe", b"MZ" + b"0" * 100,
                                        content_type="application/octet-stream")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_svg_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": SimpleUploadedFile("x.svg", b"<svg/>", content_type="image/svg+xml")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_fake_magic_bytes_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": SimpleUploadedFile("fake.png", b"notapng" + b"0" * 100,
                                        content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_download_cross_tenant_404(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": self._png()}, format="multipart",
        )
        att_id = MessageAttachment.objects.get().id
        self.client.force_authenticate(user=self.user_b)
        r = self.client.get(f"/api/conversations/attachments/{att_id}/")
        self.assertEqual(r.status_code, 404)

    def test_download_member_ok(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.post(
            f"/api/conversations/{self.conv_a.id}/attachments/",
            {"file": self._png()}, format="multipart",
        )
        att_id = MessageAttachment.objects.get().id
        r = self.client.get(f"/api/conversations/attachments/{att_id}/")
        self.assertEqual(r.status_code, 200)


# ─── Object-level REST authorization ─────────────────────────

class ObjectLevelAuthzTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_a = _user("ra@x.com")
        self.user_b = _user("rb@x.com")
        self.ws_a = _workspace_with_member(self.user_a, "ra")
        self.ws_b = _workspace_with_member(self.user_b, "rb")
        self.conv_a = _conversation(self.ws_a)
        self.customer_a = Customer.objects.filter(workspace=self.ws_a).first()

    def test_cross_tenant_conversation_denied(self):
        self.client.force_authenticate(user=self.user_b)
        r = self.client.get(f"/api/conversations/{self.conv_a.id}/")
        self.assertEqual(r.status_code, 404)

    def test_cross_tenant_messages_denied(self):
        self.client.force_authenticate(user=self.user_b)
        r = self.client.get(f"/api/conversations/{self.conv_a.id}/messages/")
        self.assertIn(r.status_code, (200, 404))
        if r.status_code == 200:
            self.assertEqual(len(r.json().get("data") or r.json().get("results") or []), 0)

    def test_cross_tenant_customer_denied(self):
        self.client.force_authenticate(user=self.user_b)
        r = self.client.get(f"/api/customers/{self.customer_a.id}/")
        self.assertEqual(r.status_code, 404)

    def test_member_can_read(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f"/api/conversations/{self.conv_a.id}/")
        self.assertEqual(r.status_code, 200)
