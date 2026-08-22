from django.urls import path
from .views import CustomerListView, CustomerDetailView, CustomerTimelineView

urlpatterns = [
    path("", CustomerListView.as_view(), name="customer-list"),
    path("<uuid:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path("<uuid:pk>/timeline/", CustomerTimelineView.as_view(), name="customer-timeline"),
]
