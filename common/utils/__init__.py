import hashlib
import json
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


def _get_fernet():
    key = settings.CREDENTIAL_ENCRYPTION_KEY.encode()[:32]
    # Pad or hash to 32 url-safe base64 bytes for Fernet
    import base64
    key_bytes = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
    return Fernet(key_bytes)


def encrypt_value(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""


def generate_webhook_signature(payload: bytes, secret: str) -> str:
    return hashlib.sha256(secret.encode() + payload).hexdigest()


def now():
    return timezone.now()


def days_ago(n: int):
    return timezone.now() - timezone.timedelta(days=n)


# ─── File upload validation ────────────────────────────────────

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | {".pdf", ".doc", ".docx", ".txt", ".csv", ".xlsx"}
ALLOWED_FILE_MIMES = ALLOWED_IMAGE_MIMES | {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_IMAGE_SIZE_MB = 5
MAX_FILE_SIZE_MB = 10


def validate_image_upload(file, max_mb: int = MAX_IMAGE_SIZE_MB):
    """Validate an uploaded image: extension, MIME, and size."""
    import os
    if file is None:
        return
    name = getattr(file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Unsupported image format: {ext}. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}")
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_IMAGE_MIMES:
        raise ValidationError(f"Unsupported image MIME type: {content_type}")
    if hasattr(file, "size") and file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Image too large. Maximum size is {max_mb} MB.")


def validate_file_upload(file, max_mb: int = MAX_FILE_SIZE_MB):
    """Validate a generic uploaded file: extension, MIME, and size."""
    import os
    if file is None:
        return
    name = getattr(file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower()
    if ext and ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(f"Unsupported file format: {ext}.")
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_FILE_MIMES:
        raise ValidationError(f"Unsupported file MIME type: {content_type}")
    if hasattr(file, "size") and file.size > max_mb * 1024 * 1024:
        raise ValidationError(f"File too large. Maximum size is {max_mb} MB.")
