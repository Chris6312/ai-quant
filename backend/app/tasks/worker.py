"""Celery application for background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config.constants import APP_NAME
from app.config.settings import get_settings

try:
    import structlog

    _LOGGER = structlog.get_logger(__name__)

    def _log_warning(event: str, **context: object) -> None:
        _LOGGER.warning(event, **context)
except ImportError:
    import logging

    _LOGGER = logging.getLogger(__name__)

    def _log_warning(event: str, **context: object) -> None:
        _LOGGER.warning("%s %s", event, context)

settings = get_settings()

celery_app = Celery(
    APP_NAME,
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.worker"],
)

celery_app.conf.task_track_started = True
celery_app.conf.worker_send_task_events = True
celery_app.conf.beat_schedule = {
    "retrain-weekly": {
        "task": "tasks.retrain_models",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
        "args": ["both"],
    }
}


@celery_app.task(name="tasks.retrain_models")
def retrain_models_task(asset_class: str = "both") -> dict[str, object]:
    """Weekly retrain task stub until the ML trainer is fully wired."""

    _log_warning(
        "ml_module_not_yet_implemented",
        asset_class=asset_class,
        message="TODO: wire app.ml.trainer into the weekly retrain task",
    )
    # TODO: import and call app.ml.trainer.WalkForwardTrainer
    # TODO: compare validation Sharpe vs deployed model
    # TODO: deploy a new model when validation improves or the run is forced
    return {
        "status": "stub",
        "asset_class": asset_class,
        "message": "TODO: wire trainer",
    }
