"""Realtime relay: iedu support_chat WebSocket → ChatPilot workspace events.

Connects to iedu's staff support-chat socket as a staff client and forwards
`new_message`/`staff_reply` events into the ChatPilot channel layer so the
frontend refetches live data via the iedu proxy endpoints. Nothing is stored
in ChatPilot's database — the iedu API is the source of truth.
"""
import asyncio
import json
import logging

import websockets
from asgiref.sync import sync_to_async

from apps.inbox.consumers import broadcast_workspace_event

logger = logging.getLogger(__name__)


class IeduBridge:
    def __init__(self, client, workspace):
        self.client = client  # IeduClient (sync httpx — called via to_thread)
        self.workspace = workspace
        self.ws_url = client.ws_url or self._derive_ws_url(client.base_url)

    @staticmethod
    def _derive_ws_url(base_url):
        # http(s)://host:port/v1/api → ws(s)://host:port/ws/support_chat/
        ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
        return ws_base.split("/v1/")[0] + "/ws/support_chat/"

    async def run_forever(self, backfill=True):
        delay = 1
        while True:
            try:
                await self._listen()
                delay = 1
            except Exception as e:
                logger.warning(
                    "[iedu-bridge] connection lost: %s — retrying in %ss", e, delay
                )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def _listen(self):
        token = await sync_to_async(lambda: self.client.access_token)()
        url = f"{self.ws_url}?token={token}"
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            logger.info("[iedu-bridge] connected to %s", self.ws_url)
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if (
                    data.get("type") == "inbox_update"
                    and data.get("event") in ("new_message", "staff_reply")
                    and data.get("conversation_id")
                ):
                    await self._notify(data["conversation_id"])

    async def _notify(self, conversation_id):
        """Push a workspace event so the frontend refetches via the proxy."""
        try:
            await sync_to_async(broadcast_workspace_event)(
                str(self.workspace.id),
                "new_message",
                {
                    "conversation_id": f"iedu_{conversation_id}",
                    "channel": "website",
                },
            )
        except Exception:
            logger.exception("[iedu-bridge] notify failed for conv %s", conversation_id)
