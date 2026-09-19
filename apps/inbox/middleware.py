"""Authentication middleware for Django Channels WebSocket connections.

Authentication methods, in order of preference:

1. HttpOnly `access_token` cookie (browser SPA — cookies are sent on the
   WS handshake for same-site requests).
2. `?ticket=` — short-lived single-use ticket from POST /api/auth/ws-ticket/
   (browser fallback when cookies can't reach the WS endpoint).
3. `?token=` — long-lived JWT in the query string. Legacy path kept for
   non-browser API clients; the frontend no longer uses it.
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.accounts.models import User


@database_sync_to_async
def get_user_from_token(token_str: str):
    try:
        token = AccessToken(token_str)
        user_id = token["user_id"]
        return User.objects.get(id=user_id)
    except (InvalidToken, TokenError, KeyError, User.DoesNotExist):
        return AnonymousUser()


@database_sync_to_async
def get_user_from_ticket(ticket: str):
    """Exchange a single-use WS ticket for a user (60s TTL, popped once)."""
    user_id = cache.get(f"ws_ticket:{ticket}")
    if not user_id:
        return AnonymousUser()
    cache.delete(f"ws_ticket:{ticket}")
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


def _parse_cookies(scope) -> dict:
    raw = b""
    for name, value in scope.get("headers", []):
        if name.lower() == b"cookie":
            raw = value
            break
    cookies = {}
    for pair in raw.decode(errors="ignore").split(";"):
        if "=" in pair:
            k, _, v = pair.strip().partition("=")
            cookies[k] = v
    return cookies


class JwtAuthMiddleware:
    """Authenticate WS connections via cookie, ticket, or legacy token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        user = AnonymousUser()

        params = {
            k: v[0] for k, v in parse_qs(scope.get("query_string", b"").decode()).items()
        }

        # 1. Single-use ticket (preferred for browsers)
        ticket = params.get("ticket")
        if ticket:
            user = await get_user_from_ticket(ticket)

        # 2. HttpOnly access-token cookie
        if not user.is_authenticated:
            from django.conf import settings

            cookie_token = _parse_cookies(scope).get(
                getattr(settings, "AUTH_COOKIE_ACCESS_NAME", "cp_access")
            )
            if cookie_token:
                user = await get_user_from_token(cookie_token)

        # 3. Legacy ?token= (non-browser API clients)
        if not user.is_authenticated and params.get("token"):
            user = await get_user_from_token(params["token"])

        scope["user"] = user
        return await self.app(scope, receive, send)


def JwtAuthMiddlewareStack(app):
    """Convenience wrapper to apply JwtAuthMiddleware."""
    return JwtAuthMiddleware(app)
