"""
Celery application instance for Media Metrics.
Broker and result backend: Redis.

Worker startup:
  celery -A app.worker worker --loglevel=info --concurrency=1 -Q default
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "media_metrics",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # One task at a time — Ollama inference is the bottleneck
    worker_prefetch_multiplier=1,
    # Only ack after the task actually finishes (safe for retries)
    task_acks_late=True,
    # Keep results for 24 hours
    result_expires=86400,
    # Suppress Celery 6.0 deprecation warning
    broker_connection_retry_on_startup=True,
)

# ── Beat schedule ─────────────────────────────────────────────────────────────
# Runs in the celery-beat container; worker picks up and executes the tasks.
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    # Fetch RSS feeds every 6 hours and queue analysis for any new articles
    "scheduled-rss-ingest": {
        "task": "app.tasks.scheduled_rss_ingest",
        "schedule": crontab(minute=0, hour="*/6"),  # 00:00, 06:00, 12:00, 18:00
    },
}
