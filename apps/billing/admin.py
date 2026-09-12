from django.contrib import admin
from .models import Plan, Subscription, Invoice, UsageRecord


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_monthly", "price_yearly", "message_limit", "team_member_limit", "is_active", "is_trial")
    list_filter = ("is_active", "is_trial")
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("workspace", "plan", "status", "billing_cycle", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "billing_cycle", "plan")
    search_fields = ("workspace__name",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "workspace", "subscription", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("invoice_number", "workspace__name")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("workspace", "period_start", "period_end", "messages_used", "ai_replies", "tokens_used")
    list_filter = ("workspace",)
    ordering = ("-period_start",)
