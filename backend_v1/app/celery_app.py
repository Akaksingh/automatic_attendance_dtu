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
