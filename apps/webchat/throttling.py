"""Rate limiting for the public webchat endpoints.

`ScopedRateThrottle` alone keys on the client IP — easily shared (NAT,
corporate proxies) and spoofable at the header level when proxies are
misconfigured. For message/session endpoints we additionally throttle on the
visitor's `session_token`, so a single abusive session is capped regardless
of source IP, and a shared IP cannot flood via one session.
"""
from rest_framework.throttling import SimpleRateThrottle


class WebchatSessionRateThrottle(SimpleRateThrottle):
    """Throttle keyed on the visitor's webchat session token.

    Falls back to IP when no session token is present (e.g. session
    creation requests), so `POST /webchat/session/` is still limited.
    """

    scope = "webchat_session"

    def get_cache_key(self, request, view):
        session_token = ""
        if hasattr(request, "data"):
            try:
                session_token = (request.data or {}).get("session_token") or ""
            except Exception:
                session_token = ""

        if session_token:
            ident = f"session:{session_token}"
        else:
            ident = self.get_ident(request)  # client IP

        return self.cache_format % {"scope": self.scope, "ident": ident}
