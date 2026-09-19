from .base import *  # noqa: F401,F403

DEBUG = True

# Dev-only throwaway encryption key — never use in production. Matches the
# legacy dev value so pre-existing encrypted credentials still decrypt.
CREDENTIAL_ENCRYPTION_KEY = env(
    "CREDENTIAL_ENCRYPTION_KEY", default="openchat-dev-encryption-key-32b!"
)
ALLOWED_HOSTS = ["*"]

# In development, allow all origins so browser previews and local tools work
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []
