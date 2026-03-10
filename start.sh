#!/usr/bin/env sh
# entrypoint script: run alembic migrations before starting the server

set -e

# apply database migrations (silently ignore if alembic is not yet configured)
echo "==> Running database migrations"
alembic upgrade head

# start the uvicorn server
RELOAD_FLAG=""
if [ "${APP_ENV:-production}" = "development" ]; then
  RELOAD_FLAG="--reload"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8080} $RELOAD_FLAG
