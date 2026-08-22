from django.urls import path
from .views import AutomationRuleListView, AutomationRuleDetailView, CommentListView

urlpatterns = [
    path("rules/", AutomationRuleListView.as_view(), name="automation-rule-list"),
    path("rules/<uuid:pk>/", AutomationRuleDetailView.as_view(), name="automation-rule-detail"),
    path("comments/", CommentListView.as_view(), name="comment-list"),
]
