from django.urls import path
from .views import DashboardView, AnalyticsChartsView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("charts/", AnalyticsChartsView.as_view(), name="charts"),
]
