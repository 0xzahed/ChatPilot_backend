import os

ENVIRONMENT = os.environ.get("DJANGO_ENV", "development")
if ENVIRONMENT == "production":
    from .production import *  # noqa: F401,F403
elif ENVIRONMENT == "test":
    from .test import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403
