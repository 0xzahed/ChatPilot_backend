from celery import shared_task
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def sync_shopify_products(integration_id):
    """Sync products from Shopify to local catalog."""
    from apps.integrations.models import Integration, SyncLog
    from apps.products.models import Product
    from apps.integrations.shopify.client import get_shopify_provider

    integration = Integration.objects.filter(id=integration_id).first()
    if not integration:
        return

    provider = get_shopify_provider(integration)
    products = provider.fetch_products()
    synced = 0

    for sp in products:
        title = sp.get("title", "")
        variants = sp.get("variants", [])
        price = variants[0].get("price", "0") if variants else "0"
        sku = variants[0].get("sku", "") if variants else ""

        product, created = Product.objects.update_or_create(
            workspace=integration.workspace,
            external_source="shopify",
            external_id=str(sp.get("id", "")),
            defaults={
                "name": title,
                "price": price,
                "sku": sku,
                "is_available": True,
            },
        )
        synced += 1

    SyncLog.objects.create(
        integration=integration,
        sync_type="manual",
        entity_type="products",
        records_synced=synced,
        status="success",
    )
    integration.last_synced_at = timezone.now()
    integration.save(update_fields=["last_synced_at"])


@shared_task
def sync_shopify_webhook(webhook_event_id):
    """Process a Shopify webhook event. Currently logs the event; extend as needed."""
    from apps.integrations.models import WebhookEvent

    webhook_event = WebhookEvent.objects.filter(id=webhook_event_id).first()
    if not webhook_event:
        return

    webhook_event.status = "processed"
    webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["status", "processed_at"])
