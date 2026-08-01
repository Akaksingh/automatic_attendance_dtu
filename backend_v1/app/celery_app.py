"""Celery application using Redis for both task messages and task results."""
from celery import Celery

from .config import settings

celery_app = Celery(
    "attendance_v1",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_default_queue = "attendance_v1"
celery_app.conf.imports = ("app.tasks",)
celery_app.conf.beat_schedule = {
    "cleanup-expired-session-photos-hourly": {
        "task": "app.tasks.cleanup_expired_session_photos",
        "schedule": 3600.0,
    },
    "cleanup-expired-refresh-tokens-daily": {
        "task": "app.tasks.cleanup_expired_refresh_tokens",
        "schedule": 86400.0,
    },
}
