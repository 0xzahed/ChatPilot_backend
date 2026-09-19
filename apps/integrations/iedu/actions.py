"""Push ChatPilot inbox actions to iedu for bridged conversations.

Each function mirrors the equivalent iedu admin-panel action through the same
admin REST endpoints, so both inboxes stay consistent. All are no-ops for
non-bridged conversations.
"""
import logging

import httpx

from .client import get_iedu_client

logger = logging.getLogger(__name__)

# ChatPilot status → iedu SupportConversation status
_STATUS_MAP = {
    "open": "open",
    "closed": "done",
    "pending": "follow_up",
}


def _iedu_id(conversation):
    return str(conversation.external_id).removeprefix("iedu_")


def _client_for(conversation):
    if conversation.config.get("bridge") != "iedu":
        return None
    return get_iedu_client(conversation.workspace)


def push_status(conversation, status):
    """Sync a ChatPilot status change to iedu."""
    client = _client_for(conversation)
    target = _STATUS_MAP.get(status)
    if not client or not target:
        return
    conv_id = _iedu_id(conversation)
    try:
        client.set_status(conv_id, target)
    except httpx.HTTPStatusError:
        # iedu only allows "done" on guest conversations — fall back to
        # "archived" for user conversations.
        if target == "done":
            try:
                client.set_status(conv_id, "archived")
            except Exception:
                logger.exception("[iedu] status sync failed (archived)")
        else:
            logger.exception("[iedu] status sync failed")
    except Exception:
        logger.exception("[iedu] status sync failed")


def push_unread(conversation):
    client = _client_for(conversation)
    if not client:
        return
    try:
        client.mark_unread(_iedu_id(conversation))
    except Exception:
        logger.exception("[iedu] mark-unread sync failed")


def push_read(conversation):
    client = _client_for(conversation)
    if not client:
        return
    try:
        client.mark_read(_iedu_id(conversation))
    except Exception:
        logger.exception("[iedu] mark-read sync failed")


def push_labels(conversation):
    """Send the conversation's current ChatPilot label names to iedu."""
    client = _client_for(conversation)
    if not client:
        return
    names = list(conversation.labels.values_list("name", flat=True))
    try:
        client.set_labels(_iedu_id(conversation), names)
    except Exception:
        logger.exception("[iedu] labels sync failed")


def push_note(conversation, content):
    """Create an iedu internal note for a ChatPilot internal note."""
    client = _client_for(conversation)
    if not client:
        return
    try:
        client.add_note(_iedu_id(conversation), content)
    except Exception:
        logger.exception("[iedu] note sync failed")
