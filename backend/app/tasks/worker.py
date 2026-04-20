"""Celery application for background jobs."""

from celery import Celery

from app.config.constants import APP_NAME
from app.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    APP_NAME,
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.worker"],
)

celery_app.conf.task_track_started = True
celery_app.conf.worker_send_task_events = True
