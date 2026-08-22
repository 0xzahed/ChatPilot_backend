from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Product, ProductVariant, ProductImage, Category
from .serializers import (
    ProductSerializer, ProductListSerializer,
    ProductVariantSerializer, ProductImageSerializer, CategorySerializer,
)
from apps.inbox.views import get_user_workspaces


class ProductListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = Product.objects.filter(workspace_id__in=ws_ids).select_related("category")

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(sku__icontains=search) |
                Q(description__icontains=search) | Q(brand__icontains=search)
            )

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category_id=category)

        is_available = self.request.query_params.get("is_available")
        if is_available == "true":
            qs = qs.filter(is_available=True)

        return qs

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Product.objects.filter(workspace_id__in=ws_ids)


class ProductVariantListView(generics.ListCreateAPIView):
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductVariant.objects.filter(product_id=self.kwargs["product_id"])

    def perform_create(self, serializer):
        product = Product.objects.get(id=self.kwargs["product_id"])
        serializer.save(product=product)


class ProductImageViewList(generics.ListCreateAPIView):
    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ProductImage.objects.filter(product_id=self.kwargs["product_id"])

    def perform_create(self, serializer):
        product = Product.objects.get(id=self.kwargs["product_id"])
        serializer.save(product=product)


class CategoryListView(generics.ListCreateAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Category.objects.filter(workspace_id__in=ws_ids)

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if ws_id not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)
