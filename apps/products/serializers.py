from rest_framework import serializers
from .models import Product, ProductVariant, ProductImage, Category


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "description", "parent", "product_count", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_product_count(self, obj):
        return obj.products.count()


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "order", "created_at"]

    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ["id", "name", "sku", "price", "stock", "attributes"]


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "description", "price", "discount_price",
            "stock", "category", "category_name", "brand", "is_available",
            "tags", "attributes", "images", "variants", "external_source",
            "external_id", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list view."""
    image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "price", "discount_price", "stock",
            "category_name", "brand", "is_available", "image_url", "created_at",
        ]

    def get_image_url(self, obj):
        first_image = obj.images.first()
        if first_image and first_image.image:
            return first_image.image.url
        return None
