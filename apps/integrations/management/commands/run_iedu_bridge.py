"""Realtime bridge to the iedu support-chat backend.

Runs as a separate process: python manage.py run_iedu_bridge

Connects to iedu's staff support WebSocket for every active integration whose
config.bridge == "iedu" and mirrors inbound user messages into the ChatPilot
inbox in realtime.
"""
import asyncio
import logging

from django.core.management.base import BaseCommand

from apps.integrations.models import Integration

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the iedu support-chat bridge (WS listener → ChatPilot inbox)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--workspace-id",
            type=str,
            default=None,
            help="Only bridge integrations for this workspace UUID.",
        )
        parser.add_argument(
            "--no-backfill",
            action="store_true",
            help="Skip the initial REST import of existing conversations.",
        )

    def handle(self, *args, **options):
        qs = Integration.objects.filter(
            integration_type="website",
            is_active=True,
            config__bridge="iedu",
        ).select_related("workspace")
        if options["workspace_id"]:
            qs = qs.filter(workspace_id=options["workspace_id"])
        integrations = list(qs)
        if not integrations:
            self.stderr.write(
                "No active iedu integrations found (config.bridge='iedu')."
            )
            return
        asyncio.run(self._run(integrations, backfill=not options["no_backfill"]))

    async def _run(self, integrations, backfill):
        from asgiref.sync import sync_to_async
        from apps.integrations.iedu.bridge import IeduBridge
        from apps.integrations.iedu.client import get_iedu_client

        tasks = []
        for integration in integrations:
            client = await sync_to_async(get_iedu_client)(integration.workspace)
            if not client:
                self.stderr.write(
                    f"Skipping workspace {integration.workspace.slug}: "
                    "iedu integration missing base_url or credentials"
                )
                continue
            self.stdout.write(
                f"Bridging workspace {integration.workspace.slug} → {client.base_url}"
            )
            bridge = IeduBridge(client, integration.workspace)
            tasks.append(bridge.run_forever(backfill=backfill))
        if tasks:
            await asyncio.gather(*tasks)
