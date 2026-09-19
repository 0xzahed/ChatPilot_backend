from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import redirect
import logging
from .models import Integration, WebhookEvent, SyncLog
from .serializers import IntegrationSerializer, WebhookEventSerializer, SyncLogSerializer
from apps.inbox.views import get_user_workspaces
from common.api_response import api_error, api_success, api_paginated
from apps.integrations.models import Integration
from apps.integrations.models import WebhookEvent
from apps.integrations.models import SyncLog

logger = logging.getLogger(__name__)


def get_integration_for_user(user, pk):
    """Fetch an integration only if the user is a member of its workspace."""
    ws_ids = get_user_workspaces(user)
    return Integration.objects.filter(id=pk, workspace_id__in=ws_ids).first()


class IntegrationListView(generics.ListCreateAPIView):
    queryset = Integration.objects.none()
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Integration.objects.filter(workspace_id__in=ws_ids)

    def create(self, request, *args, **kwargs):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)
        integration_type = request.data.get("integration_type")
        # Allow multiple integrations of the same type (e.g. multiple Facebook accounts)
        integration = Integration.objects.create(
            workspace_id=ws_id,
            integration_type=integration_type,
            status="pending",
            display_name=request.data.get("display_name", ""),
        )
        return Response(IntegrationSerializer(integration).data, status=201)


class IntegrationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return Integration.objects.filter(workspace_id__in=ws_ids)


class IntegrationConnectView(APIView):
    """Get OAuth URL for connecting an integration."""

    permission_classes = [IsAuthenticated]

    def get(self, request, integration_type):
        ws_id = request.query_params.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)

        # Create a new integration record for each connect attempt
        # (supports multiple Facebook accounts per workspace)
        integration = Integration.objects.create(
            workspace_id=ws_id,
            integration_type=integration_type,
            status="pending",
            display_name="",
        )

        from django.conf import settings
        redirect_uri = f"{settings.FRONTEND_URL}/api/integrations/callback/{integration_type}/"
        state = str(integration.id)

        if integration_type == "facebook":
            from .facebook.client import get_facebook_provider
            provider = get_facebook_provider(integration)
        elif integration_type == "instagram":
            from .instagram.client import get_instagram_provider
            provider = get_instagram_provider(integration)
        elif integration_type == "whatsapp":
            # WhatsApp Cloud API doesn't use OAuth — needs manual setup
            return api_success(data={
                "requires_manual_setup": True,
                "setup_url": "/api/integrations/whatsapp/setup/",
                "message": "WhatsApp Cloud API requires manual credentials setup.",
        }, message="Manual setup required")
        elif integration_type == "shopify":
            from .shopify.client import get_shopify_provider
            provider = get_shopify_provider(integration)
        elif integration_type == "woocommerce":
            from .woocommerce.client import get_woocommerce_provider
            provider = get_woocommerce_provider(integration)
        elif integration_type == "website":
            # Website webchat — no OAuth needed, just mark connected
            integration.status = "connected"
            integration.is_active = True
            integration.save(update_fields=["status", "is_active"])
            return api_success(data={
                "status": "connected",
                "integration": IntegrationSerializer(integration).data,
        }, message="Integration connected")
        else:
            return api_error("Unknown integration type.", code="BAD_REQUEST", status_code=400)

        auth_url = provider.get_auth_url(redirect_uri, state)
        return api_success(data={"auth_url": auth_url, "mock": not provider.is_configured()}, message="Auth URL generated")


class IntegrationCallbackView(APIView):
    """Handle OAuth callback from integration platforms.
    Redirects to frontend with code & state so frontend can complete the OAuth flow."""

    permission_classes = []  # Public — Facebook redirects here without auth

    def get(self, request, integration_type):
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        error = request.query_params.get("error", "")

        from django.conf import settings
        frontend_url = settings.FRONTEND_URL.rstrip("/")

        if error:
            return redirect(f"{frontend_url}/integrations?error={error}")

        if not code or not state:
            return redirect(f"{frontend_url}/integrations?error=missing_params")

        # Redirect to frontend integrations page with code & state
        # Frontend will call the authenticated API to complete the connection
        return redirect(
            f"{frontend_url}/integrations?callback={integration_type}&code={code}&state={state}"
        )


class IntegrationCompleteView(APIView):
    """Complete OAuth flow — called by frontend with code & state after redirect."""

    permission_classes = [IsAuthenticated]

    def post(self, request, integration_type):
        code = request.data.get("code", "")
        state = request.data.get("state", "")
        integration = get_integration_for_user(request.user, state)
        if not integration:
            return api_error("Invalid state or integration not found.", code="BAD_REQUEST", status_code=400)

        from django.conf import settings
        redirect_uri = f"{settings.FRONTEND_URL}/api/integrations/callback/{integration_type}/"

        if integration_type == "facebook":
            from .facebook.client import get_facebook_provider
            provider = get_facebook_provider(integration)
        elif integration_type == "instagram":
            from .instagram.client import get_instagram_provider
            provider = get_instagram_provider(integration)
        elif integration_type == "whatsapp":
            from .whatsapp.client import get_whatsapp_provider
            provider = get_whatsapp_provider(integration)
        elif integration_type == "shopify":
            from .shopify.client import get_shopify_provider
            provider = get_shopify_provider(integration)
        elif integration_type == "woocommerce":
            from .woocommerce.client import get_woocommerce_provider
            provider = get_woocommerce_provider(integration)
        else:
            return api_error("Unknown integration type.", code="BAD_REQUEST", status_code=400)

        try:
            credentials = provider.handle_oauth_callback(code, redirect_uri)
            if not credentials:
                return api_error("Failed to connect — no credentials returned.", code="BAD_REQUEST", status_code=400)

            # Facebook: return available pages for user selection (multi-page flow)
            if integration_type == "facebook" and "available_pages" in credentials:
                # Save user token + available pages temporarily (not connected yet)
                integration.set_credentials(credentials)
                integration.status = "pending"
                integration.config["available_pages"] = credentials["available_pages"]
                integration.save(update_fields=["credentials_encrypted", "status", "config"])
                return api_success(data={
                    "status": "pending",
                    "requires_page_selection": True,
                    "available_pages": credentials["available_pages"],
                    "integration_id": str(integration.id),
        }, message="Page selection required")

            # Other integrations: auto-connect as before
            integration.set_credentials(credentials)
            integration.status = "connected"
            integration.is_active = True
            integration.save(update_fields=["credentials_encrypted", "status", "is_active"])
            return api_success(data={"status": "connected", "integration": IntegrationSerializer(integration).data}, message="Integration connected")
        except Exception as e:
            logger.error(f"Integration complete error: {e}")
            return api_error(str(e), code="BAD_REQUEST", status_code=400)


class IntegrationSelectPagesView(APIView):
    """Connect selected Facebook Pages after OAuth page selection.

    Called by frontend after user selects which pages to connect.
    Saves page access tokens and marks the integration as connected.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        integration = get_integration_for_user(request.user, pk)
        if not integration:
            return api_error("Integration not found.", code="NOT_FOUND", status_code=404)
        if integration.integration_type != "facebook":
            return api_error("Page selection only supported for Facebook.", code="BAD_REQUEST", status_code=400)

        selected_page_ids = request.data.get("page_ids", [])
        if not selected_page_ids:
            return api_error("No pages selected.", code="BAD_REQUEST", status_code=400)

        available_pages = integration.config.get("available_pages", [])
        selected_pages = [p for p in available_pages if p.get("page_id") in selected_page_ids]

        if not selected_pages:
            return api_error("Selected pages not found in available pages.", code="BAD_REQUEST", status_code=400)

        # Save user token + selected pages in credentials
        creds = integration.get_credentials()
        creds["pages"] = selected_pages
        integration.set_credentials(creds)
        integration.status = "connected"
        integration.is_active = True
        # Store page names in config for display
        integration.config["connected_pages"] = [
            {"page_id": p["page_id"], "page_name": p["page_name"]} for p in selected_pages
        ]
        integration.save(update_fields=["credentials_encrypted", "status", "is_active", "config"])
        return api_success(data={
            "status": "connected",
            "integration": IntegrationSerializer(integration).data,
            "connected_pages": integration.config["connected_pages"],
        }, message="Integration connected")


class IntegrationDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        integration = get_integration_for_user(request.user, pk)
        if not integration:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        integration.status = "disconnected"
        integration.is_active = False
        integration.credentials_encrypted = ""
        integration.save(update_fields=["status", "is_active", "credentials_encrypted"])
        return api_success(data={"status": "disconnected"}, message="Disconnected")


class WebhookEventListView(generics.ListAPIView):
    queryset = WebhookEvent.objects.none()
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        qs = WebhookEvent.objects.filter(workspace_id__in=ws_ids)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs


class WebhookReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        ws_ids = get_user_workspaces(request.user)
        event = WebhookEvent.objects.filter(id=event_id, workspace_id__in=ws_ids).first()
        if not event:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(event.id), event.source)
        return api_success(data={"status": "replaying"}, message="Replaying")


class SyncLogListView(generics.ListAPIView):
    queryset = SyncLog.objects.none()
    serializer_class = SyncLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        ws_ids = get_user_workspaces(self.request.user)
        return SyncLog.objects.filter(integration__workspace_id__in=ws_ids)


class IntegrationSyncView(APIView):
    """Trigger a manual sync for Shopify/WooCommerce/Facebook."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        integration = get_integration_for_user(request.user, pk)
        if not integration:
            return api_error("Not found.", code="NOT_FOUND", status_code=404)
        if integration.integration_type == "shopify":
            from apps.integrations.shopify.tasks import sync_shopify_products
            sync_shopify_products.delay(str(integration.id))
        elif integration.integration_type == "woocommerce":
            from apps.integrations.woocommerce.tasks import sync_woocommerce_products
            sync_woocommerce_products.delay(str(integration.id))
        elif integration.integration_type == "facebook":
            return _sync_facebook_historical(integration)
        return api_success(data={"status": "syncing"}, message="Sync started")


def _sync_facebook_historical(integration):
    """Fetch historical conversations/messages from Facebook and save to DB."""
    from .facebook.client import get_facebook_provider
    from apps.inbox.models import Conversation, Message
    from apps.customers.models import Customer, CustomerChannel
    from django.utils import timezone

    provider = get_facebook_provider(integration)
    if not hasattr(provider, "fetch_historical_conversations"):
        return api_error("Historical sync not supported.", code="BAD_REQUEST", status_code=400)

    threads = provider.fetch_historical_conversations()
    if not threads:
        return api_success(data={"status": "completed", "synced": 0}, message="No conversations found on Facebook Page")

    workspace = integration.workspace
    creds = integration.get_credentials()
    # All configured Page IDs (multi-page aware) for sender-type detection
    configured_pages = creds.get("pages", [])
    page_ids = {p.get("page_id", "") for p in configured_pages if p.get("page_id")}
    # Legacy single-page fallback
    legacy_page_id = creds.get("page_id", "")
    if legacy_page_id:
        page_ids.add(legacy_page_id)
    synced_convs = 0
    synced_msgs = 0

    for thread in threads:
        sender_id = thread["sender_id"]
        sender_name = thread["sender_name"]
        sender_pic = thread.get("sender_pic", "")
        thread_page_id = thread.get("page_id", "")

        # Find or create customer
        channel = CustomerChannel.objects.filter(workspace=workspace, channel="facebook", external_id=sender_id).first()
        if channel:
            customer = channel.customer
            if sender_pic and not channel.profile_url:
                channel.profile_url = sender_pic
                channel.save(update_fields=["profile_url"])
        else:
            customer = Customer.objects.create(
                workspace=workspace,
                name=sender_name,
            )
            CustomerChannel.objects.create(
                customer=customer,
                workspace=workspace,
                channel="facebook",
                external_id=sender_id,
                display_name=sender_name,
                profile_url=sender_pic,
            )

        # Find or create conversation
        conv = Conversation.objects.filter(
            workspace=workspace, channel="facebook", external_id=thread["thread_id"]
        ).first()
        if not conv:
            conv = Conversation.objects.create(
                workspace=workspace,
                customer=customer,
                channel="facebook",
                status="open",
                handled_by="unassigned",
                external_id=thread["thread_id"],
                last_message_preview=thread.get("snippet", "")[:200],
            )
            synced_convs += 1

        # Save page_id in conversation config for replies
        if thread_page_id:
            conv.config["page_id"] = thread_page_id
            conv.save(update_fields=["config"])

        # Save messages
        for m in thread.get("messages", []):
            msg_ext_id = m["id"]
            if not msg_ext_id:
                continue
            existing = Message.objects.filter(external_id=msg_ext_id).first()
            if existing:
                continue

            is_from_page = (m.get("from_id") in page_ids) if page_ids else False
            sender_type = "agent" if is_from_page else "customer"
            direction = "outbound" if is_from_page else "inbound"

            # Parse timestamp
            created = m.get("created_time", "")
            try:
                from django.utils.dateparse import parse_datetime
                created_dt = parse_datetime(created)
            except Exception:
                created_dt = None

            Message.objects.create(
                conversation=conv,
                workspace=workspace,
                sender_type=sender_type,
                direction=direction,
                message_type="text",
                content=m.get("content", ""),
                status="delivered",
                external_id=msg_ext_id,
                created_at=created_dt or timezone.now(),
            )
            synced_msgs += 1

        # Update conversation timestamp
        if thread.get("updated_time"):
            try:
                from django.utils.dateparse import parse_datetime
                conv.last_message_at = parse_datetime(thread["updated_time"])
                conv.save(update_fields=["last_message_at"])

                # Broadcast via WebSocket
                from apps.inbox.consumers import broadcast_workspace_event
                broadcast_workspace_event(
                    str(workspace.id), "new_message",
                    {"conversation_id": str(conv.id), "channel": "facebook"},
                )
            except Exception:
                pass

    integration.last_synced_at = timezone.now()
    integration.save(update_fields=["last_synced_at"])

    return api_success(data={
        "status": "completed",
        "synced_conversations": synced_convs,
        "synced_messages": synced_msgs,
        "total_threads": len(threads),
        }, message="Success")


class WhatsAppSetupView(APIView):
    """Setup WhatsApp Business Cloud API credentials manually.

    WhatsApp Cloud API doesn't use OAuth — you need to manually provide
    the access token and phone number ID from Meta Business Manager.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return api_error("Invalid workspace.", code="BAD_REQUEST", status_code=400)

        access_token = request.data.get("access_token", "").strip()
        phone_number_id = request.data.get("phone_number_id", "").strip()

        if not access_token or not phone_number_id:
            return api_error("access_token and phone_number_id are required.", code="BAD_REQUEST", status_code=400)

        integration, _ = Integration.objects.get_or_create(
            workspace_id=ws_id, integration_type="whatsapp",
            defaults={"status": "pending"},
        )

        creds = integration.get_credentials() or {}
        creds["access_token"] = access_token
        creds["phone_number_id"] = phone_number_id
        integration.set_credentials(creds)
        integration.status = "connected"
        integration.is_active = True
        integration.save(update_fields=["credentials_encrypted", "status", "is_active"])

        return api_success(data={
            "status": "connected",
            "integration": IntegrationSerializer(integration).data,
        }, message="Integration connected")
