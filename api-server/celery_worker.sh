#!/bin/bash
set -e

# Display environment info for debugging
echo "Starting Celery worker with Redis URL: $REDIS_URL"
echo "Current directory: $(pwd)"
echo "Python path: $PYTHONPATH"
echo "Concurrency: $CELERY_CONCURRENCY"

# Set the Python path if not already set
export PYTHONPATH=${PYTHONPATH:-/app}

# Configure logging - ensure all logs go to stdout/stderr
export PYTHONUNBUFFERED=1

# Start Celery with proper settings
exec celery -A app.services.video_processor.celery_app worker \
  --loglevel=info \
  --concurrency=${CELERY_CONCURRENCY:-2} \
  -Q video_processing \
  --without-gossip \
  --without-mingle \
  --without-heartbeat 