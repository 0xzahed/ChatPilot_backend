from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import redirect
import logging
from .models import Integration, WebhookEvent, SyncLog
from .serializers import IntegrationSerializer, WebhookEventSerializer, SyncLogSerializer
from apps.inbox.views import get_user_workspaces

logger = logging.getLogger(__name__)


class IntegrationListView(generics.ListCreateAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Integration.objects.filter(workspace_id__in=ws_ids)

    def create(self, request, *args, **kwargs):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=400)
        integration_type = request.data.get("integration_type")
        integration, created = Integration.objects.get_or_create(
            workspace_id=ws_id, integration_type=integration_type,
            defaults={"status": "pending", "display_name": request.data.get("display_name", "")},
        )
        return Response(IntegrationSerializer(integration).data, status=201 if created else 200)


class IntegrationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Integration.objects.filter(workspace_id__in=ws_ids)


class IntegrationConnectView(APIView):
    """Get OAuth URL for connecting an integration."""

    permission_classes = [IsAuthenticated]

    def get(self, request, integration_type):
        ws_id = request.query_params.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if str(ws_id) not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=400)

        integration, _ = Integration.objects.get_or_create(
            workspace_id=ws_id, integration_type=integration_type,
            defaults={"status": "pending"},
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
            return Response({
                "requires_manual_setup": True,
                "setup_url": "/api/integrations/whatsapp/setup/",
                "message": "WhatsApp Cloud API requires manual credentials setup.",
            })
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
            return Response({
                "status": "connected",
                "integration": IntegrationSerializer(integration).data,
            })
        else:
            return Response({"error": "Unknown integration type."}, status=400)

        auth_url = provider.get_auth_url(redirect_uri, state)
        return Response({"auth_url": auth_url, "mock": not provider.is_configured()})


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
        integration = Integration.objects.filter(id=state).first()
        if not integration:
            return Response({"error": "Invalid state."}, status=400)

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
            return Response({"error": "Unknown integration type."}, status=400)

        try:
            credentials = provider.handle_oauth_callback(code, redirect_uri)
            if credentials:
                integration.set_credentials(credentials)
                integration.status = "connected"
                integration.is_active = True
                integration.save(update_fields=["credentials_encrypted", "status", "is_active"])
                return Response({"status": "connected", "integration": IntegrationSerializer(integration).data})
            return Response({"error": "Failed to connect — no credentials returned."}, status=400)
        except Exception as e:
            logger.error(f"Integration complete error: {e}")
            return Response({"error": str(e)}, status=400)


class IntegrationDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        integration = Integration.objects.filter(id=pk).first()
        if not integration:
            return Response({"error": "Not found."}, status=404)
        integration.status = "disconnected"
        integration.is_active = False
        integration.credentials_encrypted = ""
        integration.save(update_fields=["status", "is_active", "credentials_encrypted"])
        return Response({"status": "disconnected"})


class WebhookEventListView(generics.ListAPIView):
    serializer_class = WebhookEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        qs = WebhookEvent.objects.filter(workspace_id__in=ws_ids)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs


class WebhookReplayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = WebhookEvent.objects.filter(id=event_id).first()
        if not event:
            return Response({"error": "Not found."}, status=404)
        from apps.integrations.tasks import process_incoming_messages
        process_incoming_messages.delay(str(event.id), event.source)
        return Response({"status": "replaying"})


class SyncLogListView(generics.ListAPIView):
    serializer_class = SyncLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return SyncLog.objects.filter(integration__workspace_id__in=ws_ids)


class IntegrationSyncView(APIView):
    """Trigger a manual sync for Shopify/WooCommerce/Facebook."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        integration = Integration.objects.filter(id=pk).first()
        if not integration:
            return Response({"error": "Not found."}, status=404)
        if integration.integration_type == "shopify":
            from apps.integrations.shopify.tasks import sync_shopify_products
            sync_shopify_products.delay(str(integration.id))
        elif integration.integration_type == "woocommerce":
            from apps.integrations.woocommerce.tasks import sync_woocommerce_products
            sync_woocommerce_products.delay(str(integration.id))
        elif integration.integration_type == "facebook":
            return _sync_facebook_historical(integration)
        return Response({"status": "syncing"})


def _sync_facebook_historical(integration):
    """Fetch historical conversations/messages from Facebook and save to DB."""
    from .facebook.client import get_facebook_provider
    from apps.inbox.models import Conversation, Message
    from apps.customers.models import Customer, CustomerChannel
    from django.utils import timezone

    provider = get_facebook_provider(integration)
    if not hasattr(provider, "fetch_historical_conversations"):
        return Response({"error": "Historical sync not supported."}, status=400)

    threads = provider.fetch_historical_conversations()
    if not threads:
        return Response({"status": "completed", "synced": 0, "message": "No conversations found on Facebook Page."})

    workspace = integration.workspace
    page_id = integration.get_credentials().get("page_id", "")
    synced_convs = 0
    synced_msgs = 0

    for thread in threads:
        sender_id = thread["sender_id"]
        sender_name = thread["sender_name"]

        # Find or create customer
        channel = CustomerChannel.objects.filter(channel="facebook", external_id=sender_id).first()
        if channel:
            customer = channel.customer
        else:
            customer = Customer.objects.create(
                workspace=workspace,
                name=sender_name,
            )
            CustomerChannel.objects.create(
                customer=customer,
                channel="facebook",
                external_id=sender_id,
                display_name=sender_name,
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

        # Save messages
        for m in thread.get("messages", []):
            msg_ext_id = m["id"]
            if not msg_ext_id:
                continue
            existing = Message.objects.filter(external_id=msg_ext_id).first()
            if existing:
                continue

            is_from_page = (m.get("from_id") == page_id)
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

    return Response({
        "status": "completed",
        "synced_conversations": synced_convs,
        "synced_messages": synced_msgs,
        "total_threads": len(threads),
    })


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
            return Response({"error": "Invalid workspace."}, status=400)

        access_token = request.data.get("access_token", "").strip()
        phone_number_id = request.data.get("phone_number_id", "").strip()

        if not access_token or not phone_number_id:
            return Response({
                "error": "access_token and phone_number_id are required."
            }, status=400)

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

        return Response({
            "status": "connected",
            "integration": IntegrationSerializer(integration).data,
        })
