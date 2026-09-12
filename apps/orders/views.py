from decimal import Decimal
from django.db import transaction
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Order, OrderItem
from .serializers import OrderSerializer, CreateOrderSerializer
from apps.products.models import Product
from apps.customers.models import Customer
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated
from apps.orders.models import Order


class OrderListView(generics.ListCreateAPIView):
    queryset = Order.objects.none()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return OrderSerializer
        return CreateOrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        qs = Order.objects.filter(workspace_id__in=ws_ids).select_related("customer")

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)

        payment_status = self.request.query_params.get("payment_status")
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(order_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__phone__icontains=search)
            )

        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ws_ids = get_user_workspaces(request.user)
        if str(data["workspace_id"]) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)

        customer = Customer.objects.filter(id=data["customer_id"], workspace_id=data["workspace_id"]).first()
        if not customer:
            return api_error("Customer not found.", code="NOT_FOUND", status_code=404)

        # Calculate totals
        subtotal = Decimal("0")
        order_items_data = []
        for item_data in data["items"]:
            product = Product.objects.filter(id=item_data.get("product_id"), workspace_id=data["workspace_id"]).first()
            qty = int(item_data.get("quantity", 1))
            if product:
                unit_price = product.discount_price or product.price
            else:
                unit_price = Decimal(str(item_data.get("unit_price", 0)))
            total_price = unit_price * qty
            subtotal += total_price
            order_items_data.append({
                "product": product,
                "product_name": item_data.get("product_name", product.name if product else ""),
                "product_sku": item_data.get("product_sku", product.sku if product else ""),
                "variant_name": item_data.get("variant_name", ""),
                "quantity": qty,
                "unit_price": unit_price,
                "total_price": total_price,
            })

        discount = data.get("discount", Decimal("0"))
        delivery_charge = data.get("delivery_charge", Decimal("0"))
        total = subtotal - discount + delivery_charge

        # Generate a unique order number (retry on collision)
        import uuid as _uuid
        order = None
        for _ in range(5):
            order_number = f"ORD-{_uuid.uuid4().hex[:10].upper()}"
            if not Order.objects.filter(order_number=order_number).exists():
                break
        else:
            return api_error("Could not generate a unique order number.", code="INTERNAL_ERROR", status_code=500)

        order = Order.objects.create(
            order_number=order_number,
            workspace_id=data["workspace_id"],
            customer=customer,
            conversation_id=data.get("conversation_id"),
            status="pending",
            payment_method=data.get("payment_method", "cod"),
            subtotal=subtotal,
            discount=discount,
            delivery_charge=delivery_charge,
            total=total,
            shipping_address=data.get("shipping_address", ""),
            phone=data.get("phone", customer.phone),
            notes=data.get("notes", ""),
        )

        for item in order_items_data:
            OrderItem.objects.create(order=order, **item)

        # Update customer stats
        customer.total_orders += 1
        customer.total_spent += total
        customer.save(update_fields=["total_orders", "total_spent"])

        # Update conversation if linked
        if order.conversation:
            order.conversation.has_order = True
            order.conversation.save(update_fields=["has_order"])

        return Response(OrderSerializer(order).data, status=201)


class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Order.objects.filter(workspace_id__in=ws_ids)
