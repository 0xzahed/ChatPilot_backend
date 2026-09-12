from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count, Subquery, OuterRef, CharField
from .models import Product, ProductVariant, ProductImage, Category
from .serializers import (
    ProductSerializer, ProductListSerializer,
    ProductVariantSerializer, ProductImageSerializer, CategorySerializer,
)
from apps.inbox.views import get_user_workspaces
from apps.products.models import Product
from apps.products.models import ProductVariant
from apps.products.models import ProductImage
from apps.products.models import Category


class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.none()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        # Subquery for first image URL (avoids N+1)
        first_image_sq = ProductImage.objects.filter(
            product=OuterRef("pk"),
        ).order_by("order").values("image")[:1]

        qs = Product.objects.filter(workspace_id__in=ws_ids).select_related(
            "category"
        ).annotate(
            _first_image_url=Subquery(first_image_sq, output_field=CharField()),
        )

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
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Product.objects.filter(workspace_id__in=ws_ids)


class ProductVariantListView(generics.ListCreateAPIView):
    queryset = ProductVariant.objects.none()
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return ProductVariant.objects.filter(
            product_id=self.kwargs["product_id"],
            product__workspace_id__in=ws_ids,
        )

    def perform_create(self, serializer):
        ws_ids = get_user_workspaces(self.request.user)
        product = Product.objects.filter(
            id=self.kwargs["product_id"], workspace_id__in=ws_ids
        ).first()
        if not product:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Product not found.")
        serializer.save(product=product)


class ProductImageViewList(generics.ListCreateAPIView):
    queryset = ProductImage.objects.none()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return ProductImage.objects.filter(
            product_id=self.kwargs["product_id"],
            product__workspace_id__in=ws_ids,
        )

    def perform_create(self, serializer):
        ws_ids = get_user_workspaces(self.request.user)
        product = Product.objects.filter(
            id=self.kwargs["product_id"], workspace_id__in=ws_ids
        ).first()
        if not product:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Product not found.")
        serializer.save(product=product)


class CategoryListView(generics.ListCreateAPIView):
    queryset = Category.objects.none()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Category.objects.filter(workspace_id__in=ws_ids).annotate(
            product_count=Count("products"),
        )

    def perform_create(self, serializer):
        ws_id = self.request.data.get("workspace_id")
        ws_ids = get_user_workspaces(self.request.user)
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0] if ws_ids else None
        serializer.save(workspace_id=ws_id)
