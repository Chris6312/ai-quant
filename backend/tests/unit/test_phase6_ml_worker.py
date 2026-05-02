"""Phase 6 tests for ML worker queue separation and runtime visibility."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from app.api.routers import ml as ml_router
from app.config.constants import CELERY_DEFAULT_QUEUE, CELERY_ML_QUEUE
from app.config.crypto_scope import canonicalize_crypto_ml_symbol, list_crypto_ml_symbols
from app.ml.freshness import MlFreshnessResult, classify_ml_freshness
from app.tasks.ml_candles import build_ml_daily_sync_payload
from app.tasks.worker import celery_app


def test_ml_daily_sync_payload_targets_primary_intraday_ml_task() -> None:
    """The ML sync payload should target the isolated primary intraday ML task."""

    payload = build_ml_daily_sync_payload(["BTC/USD", "ETH/USD"])

    assert payload.name == "tasks.ml_candles.crypto_intraday_sync"
    assert payload.kwargs == {
        "symbols": ["BTC/USD", "ETH/USD"],
    }


def test_celery_routes_split_trading_and_ml_queues() -> None:
    """Trading candle tasks and ML candle tasks should use separate queues."""

    routes = celery_app.conf.task_routes

    assert routes["tasks.crypto_candles.*"] == {"queue": CELERY_DEFAULT_QUEUE}
    assert routes["tasks.ml_candles.*"] == {"queue": CELERY_ML_QUEUE}
    assert routes["tasks.retrain_models"] == {"queue": CELERY_ML_QUEUE}
    assert celery_app.conf.task_default_queue == CELERY_DEFAULT_QUEUE


def test_shared_ml_freshness_blocks_incomplete_coverage() -> None:
    """Fresh current-day data is not scoreable when symbol coverage is incomplete."""

    latest_candle_at = datetime(2026, 4, 24, 0, 0, tzinfo=UTC)

    freshness = classify_ml_freshness(
        latest_candle_at,
        has_missing_or_stale_symbols=True,
        current_date=date(2026, 4, 24),
    )

    assert freshness == "stale"


@pytest.mark.asyncio
async def test_prediction_guard_raises_409_when_crypto_ml_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crypto predictions should fail closed when the ML candle lane is not fresh."""

    stale_result = MlFreshnessResult(
        freshness="stale",
        latest_ml_candle_at=datetime(2026, 4, 23, 0, 0, tzinfo=UTC),
        latest_ml_candle_date=date(2026, 4, 23),
        tracked_symbol_count=15,
        symbols_with_ml_candles=14,
        missing_or_stale_symbols=("XTZ/USD",),
        can_score=False,
        block_reason="ML candles are stale or incomplete",
    )

    class _FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    def _fake_session_factory() -> _FakeSession:
        return _FakeSession()

    async def _fake_evaluate_crypto_ml_freshness(session: object) -> MlFreshnessResult:
        del session
        return stale_result

    monkeypatch.setattr(ml_router, "get_settings", lambda: object())
    monkeypatch.setattr(ml_router, "build_engine", lambda settings: object())
    monkeypatch.setattr(ml_router, "build_session_factory", lambda engine: _fake_session_factory)
    monkeypatch.setattr(
        ml_router,
        "evaluate_crypto_ml_freshness",
        _fake_evaluate_crypto_ml_freshness,
    )

    with pytest.raises(HTTPException) as exc_info:
        await ml_router._ensure_crypto_ml_can_score()

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["reason"] == "ML candles are stale or incomplete"
    assert exc_info.value.detail["missing_or_stale_symbols"] == ["XTZ/USD"]
    assert exc_info.value.detail["can_score"] is False


@pytest.mark.asyncio
async def test_prediction_guard_allows_fresh_crypto_ml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crypto predictions should continue when the ML candle lane is complete and fresh."""

    fresh_result = MlFreshnessResult(
        freshness="fresh",
        latest_ml_candle_at=datetime(2026, 4, 24, 0, 0, tzinfo=UTC),
        latest_ml_candle_date=date(2026, 4, 24),
        tracked_symbol_count=15,
        symbols_with_ml_candles=15,
        missing_or_stale_symbols=(),
        can_score=True,
        block_reason=None,
    )

    class _FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    def _fake_session_factory() -> _FakeSession:
        return _FakeSession()

    async def _fake_evaluate_crypto_ml_freshness(session: object) -> MlFreshnessResult:
        del session
        return fresh_result

    monkeypatch.setattr(ml_router, "get_settings", lambda: object())
    monkeypatch.setattr(ml_router, "build_engine", lambda settings: object())
    monkeypatch.setattr(ml_router, "build_session_factory", lambda engine: _fake_session_factory)
    monkeypatch.setattr(
        ml_router,
        "evaluate_crypto_ml_freshness",
        _fake_evaluate_crypto_ml_freshness,
    )

    result = await ml_router._ensure_crypto_ml_can_score()

    assert result == fresh_result


def test_crypto_ml_symbols_normalize_doge_to_xdg() -> None:
    """The ML lane stores Dogecoin under the Kraken canonical XDG/USD symbol."""

    symbols = list_crypto_ml_symbols()

    assert canonicalize_crypto_ml_symbol("DOGE/USD") == "XDG/USD"
    assert "XDG/USD" in symbols
    assert "DOGE/USD" not in symbols
    assert len(symbols) == 15
