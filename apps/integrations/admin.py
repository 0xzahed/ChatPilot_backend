from django.contrib import admin
from .models import Integration, WebhookEvent, SyncLog


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ("workspace", "integration_type", "status", "is_active", "last_synced_at", "created_at")
    list_filter = ("integration_type", "status", "is_active")
    search_fields = ("workspace__name", "integration_type", "display_name")
    ordering = ("-created_at",)
    readonly_fields = ("credentials_encrypted", "last_synced_at", "last_error")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("workspace", "source", "event_type", "status", "attempts", "created_at", "processed_at")
    list_filter = ("source", "status", "event_type")
    search_fields = ("event_id",)
    ordering = ("-created_at",)
    readonly_fields = ("payload", "created_at", "processed_at")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("integration", "sync_type", "entity_type", "status", "records_synced", "created_at")
    list_filter = ("sync_type", "status", "entity_type")
    search_fields = ("integration__workspace__name", "error_message")
