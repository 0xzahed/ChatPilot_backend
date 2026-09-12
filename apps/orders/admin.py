from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("total_price",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "workspace", "customer", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_status", "payment_method", "workspace")
    search_fields = ("order_number", "customer__name", "customer__phone")
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
