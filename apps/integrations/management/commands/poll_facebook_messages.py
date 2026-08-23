"""Background polling for Facebook Messenger messages.

Runs as a separate process: python manage.py poll_facebook_messages

Polls Facebook Graph API every 30 seconds for new messages and syncs them
to the database. This is a fallback for webhooks (which only work in Live mode
or for app admins/developers/testers in Development mode).
"""
import time
import logging
from django.core.management.base import BaseCommand
from apps.integrations.models import Integration

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds


class Command(BaseCommand):
    help = "Continuously poll Facebook for new messages and sync to DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=POLL_INTERVAL,
            help="Polling interval in seconds (default: 30)",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single poll cycle and exit (for testing).",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        once = options["once"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Facebook message poller (interval={interval}s)..."
            )
        )

        if once:
            self._poll_cycle()
            return

        while True:
            try:
                self._poll_cycle()
            except Exception as e:
                logger.error(f"Poll cycle error: {e}")
                self.stdout.write(self.style.ERROR(f"Poll error: {e}"))
            time.sleep(interval)

    def _poll_cycle(self):
        """Run one polling cycle — check all active Facebook integrations."""
        integrations = Integration.objects.filter(
            integration_type="facebook",
            is_active=True,
            status="connected",
        )

        if not integrations:
            return

        for integration in integrations:
            try:
                self._poll_integration(integration)
            except Exception as e:
                logger.error(f"Poll error for integration {integration.id}: {e}")
                self.stdout.write(self.style.ERROR(f"Poll error: {e}"))

    def _poll_integration(self, integration):
        """Poll a single Facebook integration for new messages."""
        from apps.integrations.facebook.client import get_facebook_provider
        from apps.integrations.views import _sync_facebook_historical
        from apps.inbox.models import Message, Conversation
        from apps.inbox.consumers import broadcast_new_message, broadcast_workspace_event
        from django.utils import timezone

        creds = integration.get_credentials()
        page_token = creds.get("page_access_token", "")
        page_id = creds.get("page_id", "")

        if not page_token or not page_id:
            self.stdout.write(self.style.WARNING(f"No page token/id for {integration.id}"))
            return

        provider = get_facebook_provider(integration)
        if not hasattr(provider, "fetch_historical_conversations"):
            self.stdout.write(self.style.WARNING("Provider has no fetch_historical_conversations"))
            return

        # Fetch conversations with messages
        threads = provider.fetch_historical_conversations()
        if not threads:
            return

        workspace = integration.workspace
        new_messages = 0
        new_conversations = 0

        self.stdout.write(
            f"[{timezone.now().strftime('%H:%M:%S')}] "
            f"Polling: {len(threads)} threads from Facebook"
        )

        for thread in threads:
            sender_id = thread["sender_id"]
            sender_name = thread["sender_name"]

            # Find or create customer
            from apps.customers.models import Customer, CustomerChannel
            channel = CustomerChannel.objects.filter(
                channel="facebook", external_id=sender_id
            ).first()
            if channel:
                customer = channel.customer
                if sender_name and customer.name == "Unknown Customer":
                    customer.name = sender_name
                    customer.save(update_fields=["name"])
                # Fetch profile picture if missing
                if not channel.profile_url:
                    try:
                        import httpx
                        presp = httpx.get(
                            f"https://graph.facebook.com/v20.0/{sender_id}/picture",
                            params={"access_token": page_token, "redirect": "false", "height": 200, "width": 200},
                            timeout=10,
                        )
                        if presp.status_code == 200:
                            pdata = presp.json().get("data", {})
                            purl = pdata.get("url", "")
                            if purl:
                                channel.profile_url = purl
                                channel.save(update_fields=["profile_url"])
                    except Exception:
                        pass
                    # Fallback: public profile pic URL (works without permissions)
                    if not channel.profile_url:
                        channel.profile_url = f"https://graph.facebook.com/{sender_id}/picture?type=large"
                        channel.save(update_fields=["profile_url"])
            else:
                customer = Customer.objects.create(
                    workspace=workspace, name=sender_name
                )
                # Fetch profile picture
                profile_url = ""
                try:
                    import httpx
                    presp = httpx.get(
                        f"https://graph.facebook.com/v20.0/{sender_id}/picture",
                        params={"access_token": page_token, "redirect": "false", "height": 200, "width": 200},
                        timeout=10,
                    )
                    if presp.status_code == 200:
                        profile_url = presp.json().get("data", {}).get("url", "")
                except Exception:
                    pass
                # Fallback: public profile pic URL
                if not profile_url:
                    profile_url = f"https://graph.facebook.com/{sender_id}/picture?type=large"
                CustomerChannel.objects.create(
                    customer=customer,
                    channel="facebook",
                    external_id=sender_id,
                    display_name=sender_name,
                    profile_url=profile_url,
                )

            # Find or create conversation
            conv = Conversation.objects.filter(
                workspace=workspace,
                channel="facebook",
                external_id=thread["thread_id"],
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
                new_conversations += 1

            # Save only NEW messages
            from django.utils.dateparse import parse_datetime

            for m in thread.get("messages", []):
                msg_ext_id = m["id"]
                if not msg_ext_id:
                    continue
                if Message.objects.filter(external_id=msg_ext_id).exists():
                    continue

                is_from_page = (m.get("from_id") == page_id)
                sender_type = "agent" if is_from_page else "customer"
                direction = "outbound" if is_from_page else "inbound"

                created_dt = None
                try:
                    created_dt = parse_datetime(m.get("created_time", ""))
                except Exception:
                    pass

                msg = Message.objects.create(
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
                new_messages += 1

                # Update conversation
                conv.last_message_at = created_dt or timezone.now()
                conv.last_message_preview = m.get("content", "")[:100]
                if not is_from_page:
                    conv.unread_count += 1
                conv.save(update_fields=[
                    "last_message_at", "last_message_preview", "unread_count"
                ])

                # Broadcast via WebSocket for real-time update
                try:
                    if not is_from_page:
                        broadcast_new_message(msg)
                except Exception:
                    pass

            # Broadcast workspace event
            if new_messages > 0:
                try:
                    broadcast_workspace_event(
                        str(workspace.id), "new_message",
                        {"conversation_id": str(conv.id), "channel": "facebook"},
                    )
                except Exception:
                    pass

        integration.last_synced_at = timezone.now()
        integration.save(update_fields=["last_synced_at"])

        if new_messages > 0 or new_conversations > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{timezone.now().strftime('%H:%M:%S')}] "
                    f"Synced: {new_conversations} new conversations, "
                    f"{new_messages} new messages"
                )
            )
