from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Avg, Q, F
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict

from apps.inbox.models import Conversation, Message
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.complaints.models import Complaint
from apps.ai.models import AIEvent
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ws_ids = get_user_workspaces(request.user)
        if not ws_ids:
            return api_success()

        ws_id = request.query_params.get("workspace_id", ws_ids[0])
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0]

        # Date range
        days = int(request.query_params.get("days", 30))
        start_date = timezone.now() - timedelta(days=days)

        conversations = Conversation.objects.filter(workspace_id=ws_id)
        messages = Message.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        orders = Order.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        customers = Customer.objects.filter(workspace_id=ws_id)
        complaints = Complaint.objects.filter(workspace_id=ws_id)

        total_conversations = conversations.count()
        open_conversations = conversations.filter(status="open").count()
        unread_messages = conversations.aggregate(total=Sum("unread_count"))["total"] or 0
        ai_handled = conversations.filter(handled_by="ai").count()
        human_handled = conversations.filter(handled_by="human").count()
        total_customers = customers.count()
        total_orders = orders.count()
        revenue = orders.filter(payment_status="paid").aggregate(total=Sum("total"))["total"] or 0
        total_complaints = complaints.count()
        open_complaints = complaints.exclude(status__in=["resolved", "closed"]).count()

        # AI automation rate
        total_with_handler = ai_handled + human_handled
        ai_automation_rate = (ai_handled / total_with_handler * 100) if total_with_handler > 0 else 0

        # Conversion rate
        conversion_rate = (total_orders / total_conversations * 100) if total_conversations > 0 else 0

        # Average response time — single query instead of N+1 loop
        from django.db.models import Min, F, ExpressionWrapper, DurationField
        convs_with_msgs = conversations.filter(status="open").annotate(
            first_customer=Min(
                "messages__created_at",
                filter=Q(messages__sender_type="customer"),
            ),
            first_reply=Min(
                "messages__created_at",
                filter=Q(messages__sender_type__in=["ai", "agent"]),
            ),
        ).exclude(first_customer__isnull=True).exclude(first_reply__isnull=True)[:100]

        response_times = []
        for conv in convs_with_msgs:
            if conv.first_customer and conv.first_reply:
                delta = (conv.first_reply - conv.first_customer).total_seconds()
                if delta >= 0:
                    response_times.append(delta)
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # Messages used (this month)
        from apps.ai.models import AIUsage
        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_usage = AIUsage.objects.filter(workspace_id=ws_id, date__gte=month_start).aggregate(
            replies=Sum("ai_replies"),
            suggestions=Sum("ai_suggestions"),
            comments=Sum("comment_automation"),
            vision=Sum("vision_requests"),
        )
        messages_used = (month_usage["replies"] or 0) + (month_usage["suggestions"] or 0) + \
                        (month_usage["comments"] or 0) + (month_usage["vision"] or 0)

        # Get plan limit
        from apps.billing.models import Subscription
        sub = Subscription.objects.filter(workspace_id=ws_id).first()
        message_limit = sub.plan.message_limit if sub else 6600

        return api_success(data={
            "total_conversations": total_conversations,
            "open_conversations": open_conversations,
            "unread_messages": unread_messages,
            "ai_handled": ai_handled,
            "human_handled": human_handled,
            "total_customers": total_customers,
            "total_orders": total_orders,
            "revenue": float(revenue),
            "conversion_rate": round(conversion_rate, 1),
            "ai_automation_rate": round(ai_automation_rate, 1),
            "avg_response_time_seconds": round(avg_response_time, 1),
            "total_complaints": total_complaints,
            "open_complaints": open_complaints,
            "messages_used": messages_used,
            "message_limit": message_limit,
            "messages_remaining": max(message_limit - messages_used, 0),
        }, message="Dashboard stats")


class AnalyticsChartsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ws_ids = get_user_workspaces(request.user)
        if not ws_ids:
            return api_success()
        ws_id = request.query_params.get("workspace_id", ws_ids[0])
        if str(ws_id) not in ws_ids:
            ws_id = ws_ids[0]

        days = int(request.query_params.get("days", 30))
        start_date = timezone.now() - timedelta(days=days)

        # Conversations over time
        conversations = Conversation.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        conv_by_day = defaultdict(int)
        for conv in conversations:
            day = conv.created_at.date().isoformat()
            conv_by_day[day] += 1

        # Orders over time
        orders = Order.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        orders_by_day = defaultdict(int)
        revenue_by_day = defaultdict(float)
        for order in orders:
            day = order.created_at.date().isoformat()
            orders_by_day[day] += 1
            revenue_by_day[day] += float(order.total)

        # Channel performance
        channel_stats = conversations.values("channel").annotate(
            count=Count("id"),
        ).order_by("-count")

        # AI automation
        ai_events = AIEvent.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        ai_by_type = defaultdict(int)
        for event in ai_events:
            ai_by_type[event.event_type] += 1

        # Customer growth
        customers = Customer.objects.filter(workspace_id=ws_id, created_at__gte=start_date)
        customer_by_day = defaultdict(int)
        for c in customers:
            day = c.created_at.date().isoformat()
            customer_by_day[day] += 1

        # Conversion funnel
        total_conversations = conversations.count()
        total_customers = customers.count()
        total_orders = orders.count()
        paid_orders = orders.filter(payment_status="paid").count()

        # AI vs Human over time
        ai_vs_human_by_day = defaultdict(lambda: {"ai": 0, "human": 0})
        for conv in conversations:
            day = conv.created_at.date().isoformat()
            if conv.handled_by == "ai":
                ai_vs_human_by_day[day]["ai"] += 1
            elif conv.handled_by == "human":
                ai_vs_human_by_day[day]["human"] += 1

        # Response time trend (simplified — average per day)
        response_by_day = defaultdict(list)
        for conv in conversations[:200]:
            first_customer_msg = conv.messages.filter(sender_type="customer").order_by("created_at").first()
            first_reply = conv.messages.filter(sender_type__in=["ai", "agent"]).order_by("created_at").first()
            if first_customer_msg and first_reply:
                delta = (first_reply.created_at - first_customer_msg.created_at).total_seconds()
                day = first_reply.created_at.date().isoformat()
                response_by_day[day].append(delta)

        return api_success(data={
            "conversations_over_time": [{"date": k, "value": v} for k, v in sorted(conv_by_day.items())],
            "orders_over_time": [{"date": k, "value": v} for k, v in sorted(orders_by_day.items())],
            "revenue_over_time": [{"date": k, "value": v} for k, v in sorted(revenue_by_day.items())],
            "channel_performance": [{"channel": c["channel"], "count": c["count"]} for c in channel_stats],
            "ai_events": [{"type": k, "count": v} for k, v in ai_by_type.items()],
            "customer_growth": [{"date": k, "value": v} for k, v in sorted(customer_by_day.items())],
            "conversion_funnel": [
                {"stage": "Conversations", "value": total_conversations},
                {"stage": "Customers", "value": total_customers},
                {"stage": "Orders", "value": total_orders},
                {"stage": "Paid Orders", "value": paid_orders},
            ],
            "ai_vs_human": [
                {"date": k, "ai": v["ai"], "human": v["human"]}
                for k, v in sorted(ai_vs_human_by_day.items())
            ],
            "response_time_trend": [
                {"date": k, "value": round(sum(v) / len(v), 1)}
                for k, v in sorted(response_by_day.items())
            ],
        }, message="Dashboard stats")
