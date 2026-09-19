from .base import *  # noqa: F401,F403

# Test-only throwaway encryption key.
CREDENTIAL_ENCRYPTION_KEY = "test-only-insecure-encryption-key-32b!"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
