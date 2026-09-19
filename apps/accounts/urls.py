from django.urls import path
from .views import (
    RegisterView, LoginView, CookieTokenRefreshView, LogoutView, MeView,
    ChangePasswordView, ForgotPasswordView, ResetPasswordView,
    SessionListView, RevokeSessionView, WsTicketView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("ws-ticket/", WsTicketView.as_view(), name="ws-ticket"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("sessions/", SessionListView.as_view(), name="sessions"),
    path("sessions/<uuid:session_id>/revoke/", RevokeSessionView.as_view(), name="revoke-session"),
]
