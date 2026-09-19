"""JWT authentication that also accepts the HttpOnly `access_token` cookie.

The browser SPA authenticates via secure cookies (set by login/refresh);
non-browser clients keep using the `Authorization: Bearer` header.

CSRF note: cookies are SameSite=Lax, which already prevents cross-site
requests from carrying them. As defense-in-depth for older browsers and
same-site edge cases, requests authenticated *via cookie* must also send the
`X-Requested-With` header on unsafe methods — a header a cross-site form
cannot set without passing CORS first.
"""
from django.conf import settings
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE = getattr(settings, "AUTH_COOKIE_ACCESS_NAME", "access_token")
CSRF_HEADER = "HTTP_X_REQUESTED_WITH"


class JWTOrCookieAuthentication(JWTAuthentication):
    def authenticate(self, request: Request):
        header = self.get_header(request)
        if header:
            # Explicit Bearer token — no extra checks needed.
            return super().authenticate(request)

        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if not raw_token:
            return None

        # Cookie-authenticated unsafe requests must carry a custom header
        # (cross-site attackers cannot set headers without passing CORS).
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.META.get(CSRF_HEADER) != "XMLHttpRequest":
                raise exceptions.PermissionDenied(
                    "Missing X-Requested-With header for cookie-authenticated request."
                )

        validated_token = self.get_validated_token(raw_token.encode())
        return self.get_user(validated_token), validated_token
