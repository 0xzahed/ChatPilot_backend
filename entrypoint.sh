#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting daphne server on port 9001..."
exec daphne -b 0.0.0.0 -p 9001 config.asgi:application
