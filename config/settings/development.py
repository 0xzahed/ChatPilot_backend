from .base import *  # noqa: F401,F403

DEBUG = True

# Dev-only throwaway encryption key — never use in production.
CREDENTIAL_ENCRYPTION_KEY = env(
    "CREDENTIAL_ENCRYPTION_KEY", default="dev-only-insecure-encryption-key-32b!"
)
ALLOWED_HOSTS = ["*"]

# In development, allow all origins so browser previews and local tools work
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []
