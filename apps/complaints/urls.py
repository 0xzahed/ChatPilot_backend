from django.urls import path
from .views import ComplaintListView, ComplaintDetailView

urlpatterns = [
    path("", ComplaintListView.as_view(), name="complaint-list"),
    path("<uuid:pk>/", ComplaintDetailView.as_view(), name="complaint-detail"),
]
