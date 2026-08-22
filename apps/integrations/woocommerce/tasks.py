from celery import shared_task
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def sync_woocommerce_products(integration_id):
    """Sync products from WooCommerce to local catalog."""
    from apps.integrations.models import Integration, SyncLog
    from apps.products.models import Product
    from apps.integrations.woocommerce.client import get_woocommerce_provider

    integration = Integration.objects.filter(id=integration_id).first()
    if not integration:
        return

    provider = get_woocommerce_provider(integration)
    products = provider.fetch_products()
    synced = 0

    for wp in products:
        product, created = Product.objects.update_or_create(
            workspace=integration.workspace,
            external_source="woocommerce",
            external_id=str(wp.get("id", "")),
            defaults={
                "name": wp.get("name", ""),
                "price": wp.get("price", "0"),
                "sku": wp.get("sku", ""),
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
