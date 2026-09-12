from django.contrib import admin
from .models import User, Session, PasswordResetToken, EmailVerificationToken


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "username", "is_platform_admin", "is_active", "last_active_at", "date_joined")
    list_filter = ("is_platform_admin", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("-date_joined",)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("user", "device_name", "device_type", "ip_address", "created_at", "expires_at", "revoked_at")
    list_filter = ("device_type",)
    search_fields = ("user__email", "device_name", "ip_address")
    ordering = ("-created_at",)
    readonly_fields = ("refresh_token_jti", "created_at")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    search_fields = ("user__email", "token")
    ordering = ["-created_at"]
    readonly_fields = ("token", "created_at")


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at")
    search_fields = ("user__email", "token")
    ordering = ["-created_at"]
    readonly_fields = ("token", "created_at")
