"""Tests for the Phase 4 runtime worker visibility API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.dependencies import get_session
from app.api.routers.runtime import _classify_ml_freshness
from app.api.routers.runtime import router as runtime_router
from app.config.crypto_scope import list_crypto_ml_symbols
from app.workers import (
    WorkerHealthService,
    WorkerKey,
    WorkerRegistry,
    WorkerStatus,
    WorkerSupervisor,
    WorkerSyncResult,
)


@dataclass(slots=True)
class _FakeWatchlistRow:
    symbol: str
    asset_class: str
    is_active: bool = True


class _FakeScalarResult:
    def __init__(self, rows: list[_FakeWatchlistRow]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterator[_FakeWatchlistRow]:
        return iter(self._rows)


class _FakeLatestCandleResult:
    def __init__(self, rows: list[tuple[str, datetime]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, datetime]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[_FakeWatchlistRow]) -> None:
        self._rows = rows
        self._latest_candle_at = datetime.now(tz=UTC)

    async def execute(self, statement: object) -> _FakeLatestCandleResult:
        del statement
        return _FakeLatestCandleResult(
            [(symbol, self._latest_candle_at) for symbol in list_crypto_ml_symbols()]
        )

    async def scalars(self, statement: object) -> _FakeScalarResult:
        del statement
        active_rows = [row for row in self._rows if row.is_active]
        return _FakeScalarResult(active_rows)


async def _override_session() -> AsyncIterator[_FakeSession]:
    yield _FakeSession(
        [
            _FakeWatchlistRow(symbol="AAPL", asset_class="stock"),
            _FakeWatchlistRow(symbol="BTC/USD", asset_class="crypto"),
        ]
    )


def test_runtime_workers_endpoint_returns_registry_snapshot() -> None:
    """The runtime endpoint should expose worker health and summary counts."""

    app = _build_runtime_app()
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        registry = client.app.state.worker_registry
        key = WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")
        now = datetime.now(tz=UTC)
        registry.register(key, source="tradier", recorded_at=now)
        registry.mark_heartbeat(key, recorded_at=now)
        registry.mark_candle_close(key, candle_close_at=now, recorded_at=now)

        response = client.get("/runtime/workers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total_workers": 1,
        "healthy_workers": 1,
        "stale_workers": 0,
        "inactive_workers": 0,
        "error_workers": 0,
    }
    assert payload["coverage"] == {
        "watchlist_targets": 1,
        "attached_workers": 1,
        "unattached_workers": 0,
        "scope_note": "Stock watchlist coverage is separate from crypto scope coverage.",
    }
    assert len(payload["workers"]) == 1
    assert payload["workers"][0]["worker_id"] == "stock:AAPL:1Day"
    assert payload["workers"][0]["status"] == WorkerStatus.RUNNING.value
    assert payload["workers"][0]["health"] == "healthy"
    assert payload["ml_workers"][0]["worker_id"] == "ml:crypto:1D"
    assert payload["ml_workers"][0]["task_name"] == "tasks.ml_candles.daily_sync"
    assert payload["ml_workers"][0]["freshness"] == "fresh"
    assert payload["ml_workers"][0]["can_score"] is True
    assert payload["ml_workers"][0]["block_reason"] is None
    assert payload["ml_workers"][0]["latest_ml_candle_date"] is not None
    assert payload["crypto_scope"]["universe_count"] >= 1
    assert (
        payload["crypto_scope"]["watchlist_count"]
        == payload["crypto_scope"]["universe_count"]
    )
    assert (
        payload["crypto_scope"]["target_runtime_count"]
        == payload["crypto_scope"]["watchlist_count"]
    )
    assert payload["crypto_scope"]["target_runtime_source"] == "derived from crypto watchlist"
    assert payload["crypto_scope"]["active_runtime_count"] == 0
    assert payload["watchlist_targets"] == [
        {
            "worker_id": "stock:AAPL:1Day",
            "symbol": "AAPL",
            "asset_class": "stock",
            "timeframe": "1Day",
            "worker_attached": True,
            "worker_status": "running",
            "worker_health": "healthy",
            "last_heartbeat_at": now.isoformat(),
            "last_error": None,
        }
    ]
    assert payload["recent_events"]
    assert payload["supervisor"]["name"] == "watchlist-sync"
    assert payload["supervisor"]["enabled"] is False


def test_runtime_workers_endpoint_honors_event_limit() -> None:
    """The runtime endpoint should cap the returned event history."""

    app = _build_runtime_app()
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        registry = client.app.state.worker_registry
        key = WorkerKey(symbol="MSFT", asset_class="stock", timeframe="1Day")
        now = datetime.now(tz=UTC)
        registry.register(key, source="tradier", recorded_at=now)
        registry.mark_running(key, recorded_at=now)
        registry.mark_error(key, "boom", recorded_at=now)

        response = client.get("/runtime/workers?event_limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["recent_events"]) == 1
    assert payload["recent_events"][0]["status"] == WorkerStatus.ERROR.value
    assert payload["coverage"]["watchlist_targets"] == 1
    assert payload["coverage"]["attached_workers"] == 0
    assert payload["coverage"]["unattached_workers"] == 1
    assert payload["crypto_scope"]["target_runtime_count"] >= 1
    assert payload["crypto_scope"]["active_runtime_count"] == 0




def test_runtime_workers_endpoint_counts_attached_crypto_workers() -> None:
    """Crypto active count should reflect attached running crypto workers only."""

    app = _build_runtime_app()
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        registry = client.app.state.worker_registry
        key = WorkerKey(symbol="KRAKEN_UNIVERSE", asset_class="crypto", timeframe="multi")
        now = datetime.now(tz=UTC)
        registry.register(key, source="kraken crypto candle scheduler", recorded_at=now)
        registry.mark_heartbeat(key, recorded_at=now)

        response = client.get("/runtime/workers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["crypto_scope"]["active_runtime_symbols"] == ["KRAKEN_UNIVERSE"]
    assert payload["crypto_scope"]["active_runtime_count"] == 1
    assert payload["crypto_scope"]["active_runtime_source"] == "attached crypto candle scheduler"




def test_ml_freshness_uses_daily_candle_date_not_eastern_shift() -> None:
    """A UTC-midnight daily candle for today should remain fresh for ML."""

    latest_candle_at = datetime(2026, 4, 24, 0, 0, tzinfo=UTC)

    freshness = _classify_ml_freshness(
        latest_candle_at,
        current_date=date(2026, 4, 24),
    )

    assert freshness == "fresh"


def test_ml_freshness_marks_current_date_partial_coverage_stale() -> None:
    """Current-date ML data is stale when some tracked symbols lag or are missing."""

    latest_candle_at = datetime(2026, 4, 24, 0, 0, tzinfo=UTC)

    freshness = _classify_ml_freshness(
        latest_candle_at,
        has_missing_or_stale_symbols=True,
        current_date=date(2026, 4, 24),
    )

    assert freshness == "stale"


def _build_runtime_app() -> FastAPI:
    app = FastAPI()
    registry = WorkerRegistry()
    app.state.worker_registry = registry
    app.state.worker_health_service = WorkerHealthService(registry)

    async def _sync() -> WorkerSyncResult:
        return WorkerSyncResult(started=0, stopped=0, unchanged=1)

    app.state.worker_supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=30,
        sync_operation=_sync,
        enabled=False,
    )
    app.include_router(runtime_router)
    return app


def test_runtime_workers_endpoint_includes_shared_ml_task_events(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Runtime events should include Celery ML task events from the shared log."""

    import app.runtime_events as runtime_events

    runtime_dir = tmp_path / ".runtime"
    monkeypatch.setattr(runtime_events, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(
        runtime_events,
        "_RUNTIME_EVENT_PATH",
        runtime_dir / "runtime_task_events.json",
    )
    runtime_events.record_runtime_task_event(
        worker_id="ml:crypto:predictions",
        status="running",
        detail="ML prediction snapshot succeeded: 15 predictions, 15 persisted",
    )

    app = _build_runtime_app()
    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        response = client.get("/runtime/workers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recent_events"][-1]["worker_id"] == "ml:crypto:predictions"
    assert payload["recent_events"][-1]["status"] == "running"
    assert payload["recent_events"][-1]["detail"] == (
        "ML prediction snapshot succeeded: 15 predictions, 15 persisted"
    )
