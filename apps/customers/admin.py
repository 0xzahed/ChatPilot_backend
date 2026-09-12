from django.contrib import admin
from .models import Customer, CustomerChannel, CustomerTimelineEvent


class CustomerChannelInline(admin.TabularInline):
    model = CustomerChannel
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "workspace", "is_vip", "total_orders", "total_spent", "created_at")
    list_filter = ("is_vip", "workspace")
    search_fields = ("name", "email", "phone")
    ordering = ("-created_at",)
    inlines = [CustomerChannelInline]


@admin.register(CustomerChannel)
class CustomerChannelAdmin(admin.ModelAdmin):
    list_display = ("customer", "channel", "external_id", "display_name", "created_at")
    list_filter = ("channel",)
    search_fields = ("external_id", "display_name", "customer__name")


@admin.register(CustomerTimelineEvent)
class CustomerTimelineEventAdmin(admin.ModelAdmin):
    list_display = ("customer", "event_type", "description", "created_at")
    list_filter = ("event_type",)
    search_fields = ("description", "customer__name")
