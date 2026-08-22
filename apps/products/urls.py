from django.urls import path
from .views import (
    ProductListView, ProductDetailView,
    ProductVariantListView, ProductImageViewList, CategoryListView,
)

urlpatterns = [
    path("", ProductListView.as_view(), name="product-list"),
    path("<uuid:pk>/", ProductDetailView.as_view(), name="product-detail"),
    path("<uuid:product_id>/variants/", ProductVariantListView.as_view(), name="product-variants"),
    path("<uuid:product_id>/images/", ProductImageViewList.as_view(), name="product-images"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
]
