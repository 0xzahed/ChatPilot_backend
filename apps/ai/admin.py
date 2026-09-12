from django.contrib import admin
from .models import AISettings, AIInstructions, AIEvent, AIUsage


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("workspace", "mode", "provider", "model_name", "updated_at")
    list_filter = ("mode", "provider")
    search_fields = ("workspace__name",)


@admin.register(AIInstructions)
class AIInstructionsAdmin(admin.ModelAdmin):
    list_display = ("workspace", "business_name", "tone", "language", "updated_at")
    search_fields = ("workspace__name", "business_name")


@admin.register(AIEvent)
class AIEventAdmin(admin.ModelAdmin):
    list_display = ("workspace", "conversation", "event_type", "model_name", "latency_ms", "created_at")
    list_filter = ("event_type", "model_name")
    search_fields = ("workspace__name",)
    ordering = ("-created_at",)


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ("workspace", "date", "ai_replies", "ai_suggestions", "tokens_input", "tokens_output")
    list_filter = ("workspace",)
    ordering = ("-date",)
