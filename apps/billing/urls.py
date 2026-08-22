from django.urls import path
from .views import PlanListView, SubscriptionView, InvoiceListView, UsageView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="plan-list"),
    path("<uuid:workspace_id>/subscription/", SubscriptionView.as_view(), name="subscription"),
    path("invoices/", InvoiceListView.as_view(), name="invoice-list"),
    path("<uuid:workspace_id>/usage/", UsageView.as_view(), name="usage"),
]
