import uuid
from django.db import models
from apps.workspaces.models import Workspace


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "categories"
        ordering = ["name"]
        unique_together = ["workspace", "name"]


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    brand = models.CharField(max_length=255, blank=True, default="")
    is_available = models.BooleanField(default=True)
    tags = models.JSONField(default=list, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    external_source = models.CharField(max_length=50, blank=True, default="")  # shopify, woocommerce, manual
    external_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "name"]),
            models.Index(fields=["workspace", "sku"]),
            models.Index(fields=["workspace", "category"]),
        ]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=255)  # e.g. "Size: XL, Color: Red"
    sku = models.CharField(max_length=100, blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "product_variants"


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=255, blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_images"
        ordering = ["order"]
