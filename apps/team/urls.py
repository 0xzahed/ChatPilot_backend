from django.urls import path
from .views import TeamListView, TeamMemberDetailView, InviteMemberView

urlpatterns = [
    path("", TeamListView.as_view(), name="team-list"),
    path("<uuid:pk>/", TeamMemberDetailView.as_view(), name="team-member-detail"),
    path("invite/", InviteMemberView.as_view(), name="team-invite"),
]
