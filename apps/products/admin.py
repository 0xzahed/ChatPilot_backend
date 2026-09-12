from django.contrib import admin
from .models import Product, ProductVariant, ProductImage, Category


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "created_at")
    list_filter = ("parent",)
    search_fields = ("name", "description")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "price", "discount_price", "stock", "is_available", "workspace", "created_at")
    list_filter = ("is_available", "workspace", "category")
    search_fields = ("name", "sku", "brand", "description")
    ordering = ("-created_at",)
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "sku", "price", "stock")
    search_fields = ("name", "sku")


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "alt_text", "order", "created_at")
    search_fields = ("alt_text",)
