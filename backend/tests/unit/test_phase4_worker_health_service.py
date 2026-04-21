"""Tests for the Phase 4 worker health service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.workers import WorkerHealth, WorkerHealthService, WorkerKey, WorkerRegistry


def test_worker_health_service_summarizes_registry_states() -> None:
    """The health service should count workers by derived health state."""

    registry = WorkerRegistry(heartbeat_ttl_s=30)
    now = datetime.now(tz=UTC)

    healthy_key = WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")
    stale_key = WorkerKey(symbol="MSFT", asset_class="stock", timeframe="1Day")
    error_key = WorkerKey(symbol="TSLA", asset_class="stock", timeframe="1Day")
    stopped_key = WorkerKey(symbol="NVDA", asset_class="stock", timeframe="1Day")

    registry.register(healthy_key, source="tradier", recorded_at=now)
    registry.mark_heartbeat(healthy_key, recorded_at=now)

    registry.register(stale_key, source="tradier", recorded_at=now)
    registry.mark_heartbeat(
        stale_key,
        recorded_at=now - timedelta(seconds=31),
    )

    registry.register(error_key, source="tradier", recorded_at=now)
    registry.mark_error(error_key, "worker crashed", recorded_at=now)

    registry.register(stopped_key, source="tradier", recorded_at=now)
    registry.mark_stopped(stopped_key, recorded_at=now)

    service = WorkerHealthService(registry)
    snapshot = service.snapshot(event_limit=2)

    assert snapshot.total_workers == 4
    assert snapshot.healthy_workers == 1
    assert snapshot.stale_workers == 1
    assert snapshot.error_workers == 1
    assert snapshot.inactive_workers == 1
    assert snapshot.workers[0].health is WorkerHealth.HEALTHY
    assert len(snapshot.recent_events) == 2
