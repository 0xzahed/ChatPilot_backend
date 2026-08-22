from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "product_sku", "variant_name", "quantity", "unit_price", "total_price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "workspace", "customer", "customer_name", "customer_phone",
            "conversation", "status", "payment_status", "payment_method",
            "subtotal", "discount", "delivery_charge", "total",
            "shipping_address", "phone", "notes", "created_by_ai",
            "items", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "order_number", "workspace", "created_at", "updated_at"]


class CreateOrderSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField(required=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    items = serializers.ListField(child=serializers.DictField(), required=True)
    shipping_address = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField(required=False, default="cod")
    delivery_charge = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    notes = serializers.CharField(required=False, allow_blank=True)
    workspace_id = serializers.UUIDField(required=True)
