from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "workspace")
    search_fields = ("title", "body", "user__email")
    ordering = ("-created_at",)
