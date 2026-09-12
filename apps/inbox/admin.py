from django.contrib import admin
from .models import Conversation, Message, MessageAttachment, Label, ConversationLabel, TypingIndicator


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender_type", "direction", "content", "external_id", "created_at")
    can_delete = False
    max_num = 50


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("customer", "channel", "status", "handled_by", "assigned_to", "last_message_at", "created_at")
    list_filter = ("channel", "status", "handled_by")
    search_fields = ("customer__name", "external_id")
    ordering = ("-last_message_at",)
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender_type", "direction", "message_type", "status", "created_at")
    list_filter = ("sender_type", "direction", "message_type", "status")
    search_fields = ("content", "external_id")
    ordering = ("-created_at",)


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("message", "file_type", "file_name", "file_size", "created_at")
    list_filter = ("file_type",)
    search_fields = ("file_name",)


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "workspace", "created_at")
    list_filter = ("workspace",)
    search_fields = ("name",)


@admin.register(ConversationLabel)
class ConversationLabelAdmin(admin.ModelAdmin):
    list_display = ("conversation", "label", "created_at")
    search_fields = ("conversation__customer__name", "label__name")


@admin.register(TypingIndicator)
class TypingIndicatorAdmin(admin.ModelAdmin):
    list_display = ("conversation", "is_ai", "is_typing", "created_at")
    list_filter = ("is_ai", "is_typing")
