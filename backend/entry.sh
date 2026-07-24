#!/usr/bin/env bash
set -e

echo "Running Alembic migrations..."
cd src
alembic upgrade head

echo "Running seed placeholder..."
python -m scripts.seed_demo_user || echo "seed placeholder failed; continuing startup"

echo "Starting the application..."
exec uvicorn main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
