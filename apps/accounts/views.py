import secrets
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .models import User, Session, PasswordResetToken, EmailVerificationToken
from common.api_response import api_error, api_success, api_paginated
from .serializers import (
    UserSerializer, RegisterSerializer, CustomTokenObtainPairSerializer,
    ChangePasswordSerializer, ForgotPasswordSerializer, ResetPasswordSerializer,
    SessionSerializer, UpdateProfileSerializer,
)


def _create_session(request, user, refresh):
    """Persist a Session row tracking the issued refresh token (JTI)."""
    try:
        jti = refresh["jti"]
        Session.objects.update_or_create(
            refresh_token_jti=jti,
            defaults={
                "user": user,
                "device_name": request.data.get("device_name", ""),
                "device_type": request.data.get("device_type", ""),
                "ip_address": request.META.get("REMOTE_ADDR"),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:1000],
                "expires_at": timezone.now() + timedelta(days=7),
            },
        )
    except Exception:
        pass


def _set_auth_cookies(response, access: str, refresh: str):
    """Attach JWTs as HttpOnly cookies (never JS-readable)."""
    secure = getattr(settings, "AUTH_COOKIE_SECURE", False)
    samesite = getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax")
    access_max_age = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    refresh_max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS_NAME, access,
        max_age=access_max_age, httponly=True, secure=secure,
        samesite=samesite, path="/",
    )
    response.set_cookie(
        settings.AUTH_COOKIE_REFRESH_NAME, refresh,
        max_age=refresh_max_age, httponly=True, secure=secure,
        samesite=samesite, path="/",
    )


def _clear_auth_cookies(response):
    response.delete_cookie(settings.AUTH_COOKIE_ACCESS_NAME, path="/")
    response.delete_cookie(settings.AUTH_COOKIE_REFRESH_NAME, path="/")


def _wants_cookies(request) -> bool:
    return bool(request.data.get("cookie_mode") or request.data.get("use_cookies"))


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        _create_session(request, user, refresh)
        return api_success(
            data={
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            message="Registration successful",
            status_code=201,
        )


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            email = request.data.get("email")
            user = User.objects.filter(email=email).first()
            if user:
                user.last_active_at = timezone.now()
                user.save(update_fields=["last_active_at"])
            # Wrap in standard envelope and track session
            try:
                refresh = RefreshToken(response.data.get("refresh"))
                if user:
                    _create_session(request, user, refresh)
            except Exception:
                pass
            if _wants_cookies(request):
                # Cookie mode: tokens go into HttpOnly cookies and are NOT
                # returned in the body, so JavaScript can never read them.
                body = api_success(
                    data={"user": UserSerializer(user).data if user else None},
                    message="Login successful",
                )
                _set_auth_cookies(
                    body, response.data["access"], response.data["refresh"]
                )
                return body
            return api_success(data=response.data, message="Login successful")
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh") or request.COOKIES.get(
                settings.AUTH_COOKIE_REFRESH_NAME
            )
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
                Session.objects.filter(
                    user=request.user, refresh_token_jti=token["jti"]
                ).update(revoked_at=timezone.now())
        except Exception:
            pass
        response = api_success(message="Logged out successfully")
        _clear_auth_cookies(response)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh access token from body OR the HttpOnly refresh cookie.

    When the refresh came from the cookie, the new access token is written
    back to the access cookie and the body omits raw tokens.
    """

    def post(self, request, *args, **kwargs):
        cookie_refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
        if cookie_refresh:
            data = request.data
            if not isinstance(data, dict):
                data = {}
            else:
                data = dict(data)
            data.setdefault("refresh", cookie_refresh)
            request._full_data = data
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and cookie_refresh:
            access = response.data.get("access")
            body = api_success(data={}, message="Token refreshed")
            _set_auth_cookies(body, access, cookie_refresh)
            return body
        return response


class WsTicketView(APIView):
    """Issue a short-lived, single-use WebSocket auth ticket.

    Browser clients exchange their cookie-authenticated session for a ticket
    and pass it as `?ticket=` on the WS handshake — avoiding long-lived JWTs
    in URLs (which leak via logs, proxies, and browser history).
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request):
        import uuid as _uuid
        from django.core.cache import cache

        ticket = _uuid.uuid4().hex
        cache.set(f"ws_ticket:{ticket}", str(request.user.id), timeout=60)
        return api_success(data={"ticket": ticket, "expires_in": 60})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_success(data=UserSerializer(request.user).data, message="User fetched")

    def patch(self, request):
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(data=UserSerializer(request.user).data, message="Profile updated")


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return api_error("Incorrect old password.", code="BAD_REQUEST", status_code=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return api_success(message="Password changed successfully")


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"]).first()
        if user:
            token = secrets.token_urlsafe(32)
            PasswordResetToken.objects.create(
                user=user, token=token,
                expires_at=timezone.now() + timedelta(hours=1),
            )
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            try:
                send_mail(
                    "Reset your password",
                    f"Click here to reset your password: {reset_url}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception:
                pass
        return api_success(message="If the email exists, a reset link has been sent.")


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_obj = PasswordResetToken.objects.filter(
            token=serializer.validated_data["token"], used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if not token_obj:
            return api_error("Invalid or expired token.", code="BAD_REQUEST", status_code=400)
        token_obj.user.set_password(serializer.validated_data["new_password"])
        token_obj.user.save()
        token_obj.used_at = timezone.now()
        token_obj.save()
        return api_success(message="Password reset successfully")


class SessionListView(generics.ListAPIView):
    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]
    queryset = Session.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return self.request.user.sessions.all()


class RevokeSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id, user=request.user)
        session.revoked_at = timezone.now()
        session.save()
        return api_success(message="Session revoked")
