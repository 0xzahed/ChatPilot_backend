"""Helpers shared by the Facebook webhook processors (Celery task + sync path).

- store incoming media (image / voice / video / file) locally, because the
  CDN URLs Facebook sends expire after a short time;
- resolve sender names + avatars using the token of the Page that actually
  received the message (not just "the first Facebook integration").
"""
import logging
import mimetypes
import os
from urllib.parse import urlparse

import httpx
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v23.0"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # Messenger's own attachment limit

MEDIA_PREVIEW = {
    "image": "📷 Photo",
    "audio": "🎤 Voice message",
    "video": "🎬 Video",
    "file": "📎 File",
}


def preview_for(incoming) -> str:
    """Conversation-list preview text for a message (text, or a media label)."""
    if incoming.content:
        return incoming.content[:100]
    atts = getattr(incoming, "attachments", None) or []
    kind = (atts[0]["type"] if atts else incoming.message_type) or "text"
    return MEDIA_PREVIEW.get(kind, "")


def _ext_for(mime: str, kind: str, url: str) -> str:
    path_ext = os.path.splitext(urlparse(url).path)[1].lower()
    if path_ext and len(path_ext) <= 5:
        return path_ext
    guessed = mimetypes.guess_extension((mime or "").split(";")[0].strip())
    if guessed:
        return guessed
    return {"image": ".jpg", "audio": ".m4a", "video": ".mp4"}.get(kind, ".bin")


_GENERIC_MIMES = {"", "application/octet-stream", "binary/octet-stream", "application/x-unknown"}
_KIND_DEFAULT_MIME = {"image": "image/jpeg", "audio": "audio/mp4", "video": "video/mp4"}


def _normalize_mime(mime: str, kind: str, url: str) -> str:
    """CDNs sometimes answer with a generic type; fall back to the extension, then the attachment kind
    (Messenger voice notes are AAC/MP4), so the browser can play it inline."""
    if mime.lower() not in _GENERIC_MIMES:
        return mime
    guessed, _ = mimetypes.guess_type(urlparse(url).path)
    if guessed and guessed.split("/")[0] in ("image", "audio", "video"):
        return guessed
    return _KIND_DEFAULT_MIME.get(kind, "application/octet-stream")


def save_incoming_attachments(message, incoming) -> int:
    """Download every attachment of an incoming message and store it. Returns count saved."""
    from apps.inbox.models import MessageAttachment

    saved = 0
    for idx, att in enumerate(getattr(incoming, "attachments", None) or []):
        url = att.get("url", "")
        kind = att.get("type", "file")
        if not url:
            continue
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        logger.warning(f"Attachment download {resp.status_code} for message {message.id}")
                        continue
                    chunks, size = [], 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES:
                            raise ValueError("attachment larger than 25 MB")
                        chunks.append(chunk)
                    mime = resp.headers.get("content-type", "").split(";")[0].strip() or "application/octet-stream"
            data = b"".join(chunks)
            mime = _normalize_mime(mime, kind, url)
            ext = _ext_for(mime, kind, url)
            name = (att.get("name") or "").strip() or f"{kind}-{str(message.id)[:8]}-{idx + 1}{ext}"
            if not os.path.splitext(name)[1]:
                name += ext
            att_obj = MessageAttachment(
                message=message, file_type=kind, file_name=name[:255],
                file_size=len(data), mime_type=mime[:100],
            )
            att_obj.file.save(name[:100], ContentFile(data), save=True)
            saved += 1
        except Exception as e:
            logger.warning(f"Failed to store {kind} attachment for message {message.id}: {e}")
    return saved


def _page_token_map():
    """page_id -> token across ALL connected Facebook integrations."""
    from apps.integrations.models import Integration

    tokens = {}
    for integ in Integration.objects.filter(
        integration_type="facebook", is_active=True, status="connected"
    ).order_by("created_at"):
        creds = integ.get_credentials()
        for p in creds.get("pages", []):
            if p.get("page_id") and p.get("page_access_token"):
                tokens[p["page_id"]] = p["page_access_token"]  # newest connection wins
    return tokens


def _lookup_profile(client, sid: str, token: str):
    """Return (name, pic) for a PSID, or ("", "") if Facebook won't tell us."""
    try:
        r = client.get(f"{GRAPH}/{sid}", params={"access_token": token, "fields": "name,profile_pic"})
        if r.status_code == 200:
            d = r.json()
            return d.get("name", ""), d.get("profile_pic", "")
    except Exception as e:
        logger.warning(f"Profile lookup failed for {sid}: {e}")
    return "", ""


def _lookup_name_via_conversations(client, page_id: str, sid: str, token: str) -> str:
    """Fallback: the Page's conversation participants list names users even
    when the profile endpoint refuses (subcode 33 / missing permissions)."""
    try:
        r = client.get(
            f"{GRAPH}/{page_id}/conversations",
            params={"access_token": token, "user_id": sid, "fields": "participants"},
        )
        if r.status_code == 200:
            for conv in r.json().get("data", []):
                for part in (conv.get("participants") or {}).get("data", []):
                    if part.get("id") == sid and part.get("name"):
                        return part["name"]
    except Exception as e:
        logger.warning(f"Conversation-participant lookup failed for {sid}: {e}")
    return ""


def resolve_profile(sid: str, page_id: str):
    """(name, pic) for a sender on a Page, trying profile API then conversations API."""
    token = _page_token_map().get(page_id)
    if not token:
        return "", ""
    with httpx.Client(timeout=10) as client:
        name, pic = _lookup_profile(client, sid, token)
        if not name:
            name = _lookup_name_via_conversations(client, page_id, sid, token)
        return name, pic


def enrich_senders(messages) -> None:
    """Fill sender_name / sender_pic on incoming messages using the owning Page's token."""
    seen = {}
    for msg in messages:
        if msg.sender_external_id:
            key = (msg.sender_external_id, msg.page_id or "")
            if key not in seen:
                seen[key] = resolve_profile(*key)
            name, pic = seen[key]
            if name:
                msg.sender_name = name
            if pic:
                msg.sender_pic = pic


def apply_sender_profile(customer, customer_channel, incoming) -> None:
    """Update an existing customer's placeholder name / avatar once we learn them."""
    if incoming.sender_name and (not customer.name or customer.name == "Unknown Customer"):
        customer.name = incoming.sender_name
        customer.save(update_fields=["name"])
    if incoming.sender_name and not customer_channel.display_name:
        customer_channel.display_name = incoming.sender_name
        customer_channel.save(update_fields=["display_name"])
    if incoming.sender_pic and not customer_channel.profile_url:
        customer_channel.profile_url = incoming.sender_pic
        customer_channel.save(update_fields=["profile_url"])
