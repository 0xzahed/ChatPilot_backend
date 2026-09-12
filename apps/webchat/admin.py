from django.contrib import admin
from .models import WebchatConfig, WebchatSession


@admin.register(WebchatConfig)
class WebchatConfigAdmin(admin.ModelAdmin):
    list_display = ("workspace", "is_enabled", "title", "position", "updated_at")
    list_filter = ("is_enabled", "position")
    search_fields = ("workspace__name", "title")


@admin.register(WebchatSession)
class WebchatSessionAdmin(admin.ModelAdmin):
    list_display = ("workspace", "visitor_name", "visitor_email", "is_online", "created_at", "last_active_at")
    list_filter = ("is_online",)
    search_fields = ("visitor_name", "visitor_email", "session_token")
