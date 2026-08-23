from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/workspaces/", include("apps.workspaces.urls")),
    path("api/conversations/", include("apps.inbox.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/complaints/", include("apps.complaints.urls")),
    path("api/labels/", include("apps.labels.urls")),
    path("api/automation/", include("apps.automation.urls")),
    path("api/ai/", include("apps.ai.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    path("api/webhooks/", include("apps.webhooks.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/billing/", include("apps.billing.urls")),
    path("api/usage/", include("apps.usage.urls")),
    path("api/team/", include("apps.team.urls")),
    path("api/audit/", include("apps.audit.urls")),
    path("api/webchat/", include("apps.webchat.urls")),
    path("api/admin/", include("apps.platform_admin.urls")),

    # Webhook endpoints for external platforms
    path("webhooks/meta/", include("apps.integrations.facebook.urls_webhook")),
    path("webhooks/whatsapp/", include("apps.integrations.whatsapp.urls_webhook")),
    path("webhooks/shopify/", include("apps.integrations.shopify.urls_webhook")),

    # API docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

# Serve static files (webchat widget)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static("/static/", document_root=settings.BASE_DIR / "static")
