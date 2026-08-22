from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Integration, WebhookEvent, SyncLog
from .serializers import IntegrationSerializer, WebhookEventSerializer, SyncLogSerializer
from apps.inbox.views import get_user_workspaces


class IntegrationListView(generics.ListCreateAPIView):
    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ws_ids = get_user_workspaces(self.request.user)
        return Integration.objects.filter(workspace_id__in=ws_ids)

    def create(self, request, *args, **kwargs):
        ws_id = request.data.get("workspace_id")
        ws_ids = get_user_workspaces(request.user)
        if ws_id not in ws_ids:
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
        if ws_id not in ws_ids:
            return Response({"error": "Invalid workspace."}, status=400)

        integration, _ = Integration.objects.get_or_create(
            workspace_id=ws_id, integration_type=integration_type,
            defaults={"status": "pending"},
        )

        from django.conf import settings
        redirect_uri = f"{settings.FRONTEND_URL}/integrations/{integration_type}/callback"
        state = str(integration.id)

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

        auth_url = provider.get_auth_url(redirect_uri, state)
        return Response({"auth_url": auth_url, "mock": not provider.is_configured()})


class IntegrationCallbackView(APIView):
    """Handle OAuth callback from integration platforms."""

    permission_classes = [IsAuthenticated]

    def get(self, request, integration_type):
        code = request.query_params.get("code", "")
        state = request.query_params.get("state", "")
        integration = Integration.objects.filter(id=state).first()
        if not integration:
            return Response({"error": "Invalid state."}, status=400)

        from django.conf import settings
        redirect_uri = f"{settings.FRONTEND_URL}/integrations/{integration_type}/callback"

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

        credentials = provider.handle_oauth_callback(code, redirect_uri)
        if credentials:
            integration.set_credentials(credentials)
            integration.status = "connected"
            integration.is_active = True
            integration.save(update_fields=["credentials_encrypted", "status", "is_active"])
            return Response({"status": "connected", "integration": IntegrationSerializer(integration).data})
        return Response({"error": "Failed to connect."}, status=400)


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
    """Trigger a manual sync for Shopify/WooCommerce."""

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
        return Response({"status": "syncing"})
