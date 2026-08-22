import hashlib
import json
from cryptography.fernet import Fernet
from django.conf import settings
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
