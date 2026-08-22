from django.urls import path
from .views import WebchatConfigView

urlpatterns = [
    path("config/<uuid:workspace_id>/", WebchatConfigView.as_view(), name="webchat-config"),
]
