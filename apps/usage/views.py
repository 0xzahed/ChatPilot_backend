from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta
from apps.ai.models import AIUsage
from apps.billing.models import Subscription
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated


class UsageSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        ws_ids = get_user_workspaces(request.user)
        if str(workspace_id) not in ws_ids:
            return api_error("Invalid workspace.", code="FORBIDDEN", status_code=403)

        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_usage = AIUsage.objects.filter(workspace_id=workspace_id, date__gte=month_start).aggregate(
            ai_replies=Sum("ai_replies"),
            ai_suggestions=Sum("ai_suggestions"),
            comment_automation=Sum("comment_automation"),
            vision_requests=Sum("vision_requests"),
            tokens_input=Sum("tokens_input"),
            tokens_output=Sum("tokens_output"),
            estimated_cost=Sum("estimated_cost"),
        )

        messages_used = (month_usage["ai_replies"] or 0) + (month_usage["ai_suggestions"] or 0) + \
                        (month_usage["comment_automation"] or 0) + (month_usage["vision_requests"] or 0)

        sub = Subscription.objects.filter(workspace_id=workspace_id).first()
        message_limit = sub.plan.message_limit if sub else 6600
        team_member_limit = sub.plan.team_member_limit if sub else 3

        from apps.workspaces.models import WorkspaceMembership
        team_members = WorkspaceMembership.objects.filter(workspace_id=workspace_id).count()

        return api_success(data={
            "messages_used": messages_used,
            "message_limit": message_limit,
            "messages_remaining": max(message_limit - messages_used, 0),
            "ai_replies": month_usage["ai_replies"] or 0,
            "ai_suggestions": month_usage["ai_suggestions"] or 0,
            "comment_automation": month_usage["comment_automation"] or 0,
            "vision_requests": month_usage["vision_requests"] or 0,
            "tokens_input": month_usage["tokens_input"] or 0,
            "tokens_output": month_usage["tokens_output"] or 0,
            "estimated_cost": float(month_usage["estimated_cost"] or 0),
            "team_members": team_members,
            "team_member_limit": team_member_limit,
            "period_start": month_start.isoformat(),
            "period_end": today.isoformat(),
        }, message="Usage stats")
