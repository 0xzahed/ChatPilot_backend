from django.urls import path
from .views import LabelListView, LabelDetailView

urlpatterns = [
    path("", LabelListView.as_view(), name="label-list"),
    path("<uuid:pk>/", LabelDetailView.as_view(), name="label-detail"),
]
