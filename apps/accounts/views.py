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
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from .models import User, Session, PasswordResetToken, EmailVerificationToken
from common.api_response import api_error, api_success, api_paginated
from .serializers import (
    UserSerializer, RegisterSerializer, CustomTokenObtainPairSerializer,
    ChangePasswordSerializer, ForgotPasswordSerializer, ResetPasswordSerializer,
    SessionSerializer, UpdateProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
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

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            email = request.data.get("email")
            user = User.objects.filter(email=email).first()
            if user:
                user.last_active_at = timezone.now()
                user.save(update_fields=["last_active_at"])
            # Wrap in standard envelope
            return api_success(data=response.data, message="Login successful")
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            Session.objects.filter(user=request.user, refresh_token_jti=token["jti"]).update(revoked_at=timezone.now())
        except Exception:
            pass
        return api_success(message="Logged out successfully")


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

    def get_queryset(self):
        return self.request.user.sessions.all()


class RevokeSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(Session, id=session_id, user=request.user)
        session.revoked_at = timezone.now()
        session.save()
        return api_success(message="Session revoked")
