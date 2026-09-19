"""REST client for the iedu support-chat backend.

Used by the bridge (inbound mirroring) and by _send_to_channel (outbound
agent replies). Authenticates as a staff/superuser account via mobile+password
against the iedu admin support_chat API.
"""
import threading

import httpx


class IeduClient:
    def __init__(self, base_url, mobile, password, ws_url=""):
        self.base_url = base_url.rstrip("/")
        self.mobile = mobile
        self.password = password
        self.ws_url = ws_url
        self._access = None
        self._refresh = None
        self.user_id = None  # iedu account id — set on login
        self._lock = threading.Lock()

    # ─── Auth ────────────────────────────────────────────────
    def login(self):
        resp = httpx.post(
            f"{self.base_url}/account/login",
            json={"mobile": self.mobile, "password": self.password},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access = data.get("access") or (data.get("data") or {}).get("access")
        self._refresh = data.get("refresh") or (data.get("data") or {}).get("refresh")
        self.user_id = data.get("id") or (data.get("data") or {}).get("id")
        if not self._access:
            raise RuntimeError(f"iedu login failed: {data.get('msg') or data}")
        return self._access

    @property
    def access_token(self):
        with self._lock:
            if not self._access:
                self.login()
            return self._access

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method, path, **kwargs):
        resp = httpx.request(
            method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs
        )
        if resp.status_code == 401:
            # Token expired — force re-login and retry once
            self._access = None
            resp = httpx.request(
                method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs
            )
        resp.raise_for_status()
        return resp.json()

    # ─── Support chat admin API ─────────────────────────────
    def get_conversations(self, limit=100):
        """Fetch ALL conversations across pagination."""
        convs, page = [], 1
        while True:
            data = self._request(
                "GET", "/support/admin/conversations",
                params={"page": page, "limit": limit},
            )
            items = data.get("data") or []
            convs.extend(items)
            if not data.get("has_next"):
                return convs
            page = data.get("next_page") or page + 1

    def get_messages(self, conversation_id, limit=100, all_pages=False):
        """Fetch messages for a conversation (newest-first from iedu).

        all_pages=False → first page only (covers recent live events).
        all_pages=True  → every page (full history backfill).
        """
        conv, msgs, page = {}, [], 1
        while True:
            data = self._request(
                "GET", f"/support/admin/conversations/{conversation_id}",
                params={"page": page, "limit": limit},
            )
            inner = data.get("data") or {}
            conv = inner.get("conversation") or conv
            msgs.extend(inner.get("messages") or [])
            if not all_pages or page >= (inner.get("total_pages") or 1):
                return conv, msgs
            page += 1

    def reply(self, conversation_id, content, message_type="Text"):
        return self._request(
            "POST",
            f"/support/admin/conversations/{conversation_id}/reply",
            json={"content": content, "message_type": message_type},
        )

    # ─── Admin actions (same endpoints the iedu panel uses) ───
    def set_status(self, conversation_id, status):
        return self._request(
            "POST",
            f"/support/admin/conversations/{conversation_id}/status",
            json={"status": status},
        )

    def mark_unread(self, conversation_id):
        return self._request(
            "POST", f"/support/admin/conversations/{conversation_id}/mark-unread"
        )

    def mark_read(self, conversation_id):
        return self._request(
            "POST", f"/support/admin/conversations/{conversation_id}/mark-read"
        )

    def set_labels(self, conversation_id, labels):
        return self._request(
            "POST",
            f"/support/admin/conversations/{conversation_id}/labels",
            json={"labels": labels},
        )

    def add_note(self, conversation_id, content):
        return self._request(
            "POST",
            f"/support/admin/conversations/{conversation_id}/notes",
            json={"content": content},
        )


def get_iedu_client(workspace):
    """Build a client from the workspace's active iedu-bridged integration."""
    from apps.integrations.models import Integration

    integration = Integration.objects.filter(
        workspace=workspace,
        integration_type="website",
        is_active=True,
        config__bridge="iedu",
    ).first()
    if not integration:
        return None
    cfg = integration.config or {}
    base_url = cfg.get("base_url")
    if not base_url:
        return None
    creds = integration.get_credentials()
    return IeduClient(
        base_url=base_url,
        mobile=creds.get("mobile", ""),
        password=creds.get("password", ""),
        ws_url=cfg.get("ws_url", ""),
    )
