#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

# Optional: bootstrap a platform admin (set both vars to enable)
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
U = get_user_model()
e = os.environ['DJANGO_SUPERUSER_EMAIL']
if not U.objects.filter(email=e).exists():
    u = U.objects.create_superuser(username=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'), email=e, password=os.environ['DJANGO_SUPERUSER_PASSWORD'])
    u.is_platform_admin = True
    u.save()
    print('Created platform admin', e)
"
fi

echo "Starting daphne server on port 8000..."
exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
