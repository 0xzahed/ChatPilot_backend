from django.contrib import admin
from .models import Complaint


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("customer", "workspace", "title", "status", "priority", "assigned_to", "detected_by_ai", "created_at")
    list_filter = ("status", "priority", "detected_by_ai", "workspace")
    search_fields = ("title", "description", "customer__name", "customer__phone")
    ordering = ("-created_at",)
