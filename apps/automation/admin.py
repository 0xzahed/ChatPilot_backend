from django.contrib import admin
from .models import AutomationRule, Comment


@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "rule_type", "is_active", "use_ai", "channel", "created_at")
    list_filter = ("rule_type", "is_active", "use_ai", "channel", "workspace")
    search_fields = ("name", "response_template")
    ordering = ("-created_at",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("workspace", "channel", "author_name", "content", "is_replied", "is_auto_replied", "created_at")
    list_filter = ("channel", "is_replied", "is_auto_replied", "workspace")
    search_fields = ("author_name", "content", "external_id")
    ordering = ("-created_at",)
