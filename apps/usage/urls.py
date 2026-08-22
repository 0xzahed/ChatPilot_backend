from django.urls import path
from .views import UsageSummaryView

urlpatterns = [
    path("<uuid:workspace_id>/", UsageSummaryView.as_view(), name="usage-summary"),
]
