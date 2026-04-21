"""Tests for the Phase 4 runtime worker visibility API."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.runtime import router as runtime_router
from app.workers import (
    WorkerHealthService,
    WorkerKey,
    WorkerRegistry,
    WorkerStatus,
    WorkerSupervisor,
    WorkerSyncResult,
)


def test_runtime_workers_endpoint_returns_registry_snapshot() -> None:
    """The runtime endpoint should expose worker health and summary counts."""

    app = _build_runtime_app()
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
    assert len(payload["workers"]) == 1
    assert payload["workers"][0]["worker_id"] == "stock:AAPL:1Day"
    assert payload["workers"][0]["status"] == WorkerStatus.RUNNING.value
    assert payload["workers"][0]["health"] == "healthy"
    assert payload["recent_events"]
    assert payload["supervisor"]["name"] == "watchlist-sync"
    assert payload["supervisor"]["enabled"] is False


def test_runtime_workers_endpoint_honors_event_limit() -> None:
    """The runtime endpoint should cap the returned event history."""

    app = _build_runtime_app()
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


def _build_runtime_app() -> FastAPI:
    app = FastAPI()
    registry = WorkerRegistry()
    app.state.worker_registry = registry
    app.state.worker_health_service = WorkerHealthService(registry)

    async def _sync() -> WorkerSyncResult:
        return WorkerSyncResult(started=0, stopped=0, unchanged=1)

    app.state.worker_supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=30.0,
        sync_operation=_sync,
        enabled=False,
    )
    app.include_router(runtime_router)
    return app
