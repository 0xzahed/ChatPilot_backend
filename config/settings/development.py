from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# In development, allow all origins so browser previews and local tools work
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []
