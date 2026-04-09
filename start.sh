#!/usr/bin/env sh
# entrypoint script: run alembic migrations before starting the server

set -e

# apply database migrations — retry up to 10 times with 3-second backoff to
# handle transient DB unavailability on cold starts (e.g. Fly.io scale-to-zero)
echo "==> Running database migrations"
MAX_TRIES=10
WAIT_SECS=3
n=0
until alembic upgrade head; do
  n=$((n + 1))
  if [ "$n" -ge "$MAX_TRIES" ]; then
    echo "==> Database migrations failed after $MAX_TRIES attempts, aborting"
    exit 1
  fi
  echo "==> Migration attempt $n failed, retrying in ${WAIT_SECS}s..."
  sleep "$WAIT_SECS"
done

# start the uvicorn server
RELOAD_FLAG=""
if [ "${APP_ENV:-production}" = "development" ]; then
  RELOAD_FLAG="--reload"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8080} $RELOAD_FLAG
