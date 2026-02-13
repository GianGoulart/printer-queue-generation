"""Celery tasks."""

from app.celery_app import celery_app

# Import all tasks to register them with Celery
from app.tasks.reindex import reindex_assets  # noqa: F401
from app.tasks.process_job import process_job  # noqa: F401
from app.tasks.image_packing import process_image_packing  # noqa: F401


@celery_app.task(name="app.tasks.dummy_task")
def dummy_task(x: int, y: int) -> int:
    """Dummy task for testing Celery setup."""
    return x + y


@celery_app.task(name="app.tasks.health_check")
def health_check() -> dict:
    """Health check task."""
    return {"status": "ok", "worker": "ready"}


# Export all tasks
__all__ = ["dummy_task", "health_check", "reindex_assets", "process_job", "process_image_packing"]
