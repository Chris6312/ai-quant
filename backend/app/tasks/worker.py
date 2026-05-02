"""Celery application for background jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config.constants import (
    APP_NAME,
    CELERY_DEFAULT_QUEUE,
    CELERY_ML_QUEUE,
)
from app.config.settings import get_settings
from app.runtime_events import record_runtime_task_event

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
    include=[
        "app.tasks.worker",
        "app.tasks.crypto_candles",
        "app.tasks.ml_candles",
        "app.tasks.news_sentiment",
        "app.tasks.stock_screener",
    ],
)

celery_app.conf.update(
    task_track_started=True,
    worker_send_task_events=True,
    task_default_queue=CELERY_DEFAULT_QUEUE,
    task_routes={
        "tasks.crypto_candles.*": {"queue": CELERY_DEFAULT_QUEUE},
        "tasks.ml_candles.*": {"queue": CELERY_ML_QUEUE},
        "tasks.ml_predictions.run": {"queue": CELERY_ML_QUEUE},
        "tasks.retrain_models": {"queue": CELERY_ML_QUEUE},
        "tasks.news_sentiment.*": {"queue": CELERY_ML_QUEUE},
        "tasks.stock_screener.*": {"queue": CELERY_DEFAULT_QUEUE},
    },
    timezone="America/New_York",
    beat_schedule={
        "news-sentiment-crypto-refresh": {
            "task": "tasks.news_sentiment.daily_crypto_sync",
            "schedule": crontab(hour="2,6,10,14,18,22", minute=30),
        },
        "ml-crypto-intraday-candle-sync": {
            "task": "tasks.ml_candles.crypto_intraday_sync",
            "schedule": crontab(hour=3, minute=15),
        },
        "ml-crypto-context-candle-sync": {
            "task": "tasks.ml_candles.crypto_context_sync",
            "schedule": crontab(hour=3, minute=45),
        },
        "ml-stock-intraday-candle-sync": {
            "task": "tasks.ml_candles.stock_intraday_sync",
            "schedule": crontab(hour=18, minute=30, day_of_week=6),
        },
        "ml-prediction-snapshot": {
            "task": "tasks.ml_predictions.run",
            "schedule": crontab(hour=8, minute=55),
            "kwargs": {"asset_class": "crypto", "limit": 200},
        },
        "retrain-weekly": {
            "task": "tasks.retrain_models",
            "schedule": crontab(hour=2, minute=0, day_of_week=0),
            "args": ["both"],
        },
    },
)


@celery_app.task(name="tasks.retrain_models")
def retrain_models_task(asset_class: str = "both") -> dict[str, object]:
    """Weekly retrain task stub until the ML trainer is fully wired."""

    _log_warning(
        "ml_module_not_yet_implemented",
        asset_class=asset_class,
        message="TODO: wire app.ml.trainer into the weekly retrain task",
    )
    return {
        "status": "stub",
        "asset_class": asset_class,
        "message": "TODO: wire trainer",
    }


@celery_app.task(name="tasks.ml_predictions.run")
def run_ml_predictions_task(
    asset_class: str | None = "crypto",
    limit: int = 200,
) -> dict[str, object]:
    """Generate and persist an ML prediction snapshot from the ML queue."""

    import asyncio

    from app.api.routers.ml import generate_prediction_snapshot

    asset_label = asset_class or "both"
    record_runtime_task_event(
        worker_id="ml:crypto:predictions",
        status="starting",
        detail=f"ML prediction snapshot started for {asset_label}",
    )
    try:
        result = asyncio.run(
            generate_prediction_snapshot(
                asset_class=asset_class,
                limit=limit,
            )
        )
    except Exception as exc:
        record_runtime_task_event(
            worker_id="ml:crypto:predictions",
            status="error",
            detail=f"ML prediction snapshot failed: {type(exc).__name__}: {exc}",
        )
        raise

    payload = dict(result)
    count = payload.get("count")
    persisted_count = payload.get("persisted_count")
    record_runtime_task_event(
        worker_id="ml:crypto:predictions",
        status="running",
        detail=(
            "ML prediction snapshot succeeded: "
            f"{count} predictions, {persisted_count} persisted"
        ),
    )
    return payload
