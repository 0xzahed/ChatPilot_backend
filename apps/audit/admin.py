from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "action", "resource_type", "resource_id", "created_at")
    list_filter = ("action", "resource_type", "workspace")
    search_fields = ("action", "resource_type", "resource_id", "description", "user__email")
    ordering = ("-created_at",)
