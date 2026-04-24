"""Phase 6 tests for ML worker queue separation and runtime visibility."""

from __future__ import annotations

from app.config.constants import CELERY_DEFAULT_QUEUE, CELERY_ML_QUEUE
from app.tasks.ml_candles import build_ml_daily_sync_payload
from app.tasks.worker import celery_app


def test_ml_daily_sync_payload_targets_ml_task() -> None:
    """The ML daily sync payload should target the isolated ML task."""

    payload = build_ml_daily_sync_payload(["BTC/USD", "ETH/USD"])

    assert payload.name == "tasks.ml_candles.daily_sync"
    assert payload.kwargs == {
        "symbols": ["BTC/USD", "ETH/USD"],
        "lookback_days": 730,
    }


def test_celery_routes_split_trading_and_ml_queues() -> None:
    """Trading candle tasks and ML candle tasks should use separate queues."""

    routes = celery_app.conf.task_routes

    assert routes["tasks.crypto_candles.*"] == {"queue": CELERY_DEFAULT_QUEUE}
    assert routes["tasks.ml_candles.*"] == {"queue": CELERY_ML_QUEUE}
    assert routes["tasks.retrain_models"] == {"queue": CELERY_ML_QUEUE}
    assert celery_app.conf.task_default_queue == CELERY_DEFAULT_QUEUE
