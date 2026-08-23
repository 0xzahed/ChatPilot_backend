"""JWT authentication middleware for Django Channels WebSocket connections.

Reads the JWT access token from the query string (`?token=...`) and
authenticates the user, populating `scope["user"]` so that consumers
can check authentication the same way they do for session-based auth.
"""
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
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


class JwtAuthMiddleware:
    """Middleware that authenticates a WebSocket connection via JWT token
    passed in the query string as `?token=...`.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Parse token from query string
        query_string = scope.get("query_string", b"").decode()
        params = dict(
            pair.split("=", 1) for pair in query_string.split("&") if "=" in pair
        )
        token = params.get("token")

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.app(scope, receive, send)


def JwtAuthMiddlewareStack(app):
    """Convenience wrapper to apply JwtAuthMiddleware."""
    return JwtAuthMiddleware(app)
