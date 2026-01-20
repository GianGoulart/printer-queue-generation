"""Celery client for API to dispatch tasks."""

from celery import Celery

from app.config import settings

# Create Celery client (just for sending tasks, not executing)
celery_app = Celery(
    "printer_queue_api",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
