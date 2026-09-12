from django.contrib import admin
from .models import Workspace, WorkspaceMembership, WorkspaceSettings


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("-created_at",)


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "role", "joined_at")
    list_filter = ("role",)
    search_fields = ("user__email", "workspace__name")
    ordering = ("-joined_at",)


@admin.register(WorkspaceSettings)
class WorkspaceSettingsAdmin(admin.ModelAdmin):
    list_display = ("workspace", "updated_at")
    search_fields = ("workspace__name",)
