from django.urls import path
from .views import WebchatConfigView, WebchatPublicConfigView, WebchatSessionView, WebchatMessageView

urlpatterns = [
    path("config/<uuid:workspace_id>/", WebchatConfigView.as_view(), name="webchat-config"),
    path("public/<uuid:workspace_id>/", WebchatPublicConfigView.as_view(), name="webchat-public-config"),
    path("session/", WebchatSessionView.as_view(), name="webchat-session"),
    path("message/", WebchatMessageView.as_view(), name="webchat-message"),
]
