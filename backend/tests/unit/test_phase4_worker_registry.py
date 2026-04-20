"""Tests for the Phase 4 worker registry foundation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.workers import WorkerHealth, WorkerKey, WorkerRegistry, WorkerStatus


@pytest.fixture
def worker_key() -> WorkerKey:
    """Return a stable worker key for registry tests."""

    return WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")


def test_worker_registry_tracks_lifecycle_and_task_refs(worker_key: WorkerKey) -> None:
    """A registry entry should move cleanly through start and run states."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    task_ref = object()
    started_at = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)

    starting = registry.register(
        worker_key,
        source="tradier",
        task_ref=task_ref,
        task_name="worker:AAPL:1Day",
        recorded_at=started_at,
    )
    running = registry.mark_running(worker_key, recorded_at=started_at + timedelta(seconds=1))

    assert starting.status is WorkerStatus.STARTING
    assert running.status is WorkerStatus.RUNNING
    assert registry.get_task_ref(worker_key) is task_ref
    assert registry.get(worker_key) == running
    assert registry.list_snapshots()[0].task_name == "worker:AAPL:1Day"


def test_worker_registry_derives_health_from_heartbeat(worker_key: WorkerKey) -> None:
    """Healthy workers should turn stale when the heartbeat ages out."""

    registry = WorkerRegistry(heartbeat_ttl_s=30)
    base_time = datetime.now(tz=UTC) - timedelta(seconds=10)
    registry.register(worker_key, source="tradier", recorded_at=base_time)
    healthy = registry.mark_heartbeat(worker_key, recorded_at=base_time)

    assert healthy.health is WorkerHealth.HEALTHY

    stale_time = datetime.now(tz=UTC) - timedelta(seconds=31)
    registry.mark_heartbeat(worker_key, recorded_at=stale_time)
    stale_snapshot = registry.get(worker_key)
    assert stale_snapshot is not None
    assert stale_snapshot.health is WorkerHealth.STALE


def test_worker_registry_records_candle_close_and_error(worker_key: WorkerKey) -> None:
    """Candle timestamps and terminal errors should be visible in the snapshot."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    recorded_at = datetime(2026, 4, 20, 13, 0, tzinfo=UTC)
    candle_close_at = recorded_at - timedelta(minutes=1)

    registry.register(worker_key, source="tradier", recorded_at=recorded_at)
    registry.mark_heartbeat(worker_key, recorded_at=recorded_at)
    running = registry.mark_candle_close(
        worker_key,
        candle_close_at,
        recorded_at=recorded_at + timedelta(seconds=5),
    )
    errored = registry.mark_error(
        worker_key,
        "broker disconnected",
        recorded_at=recorded_at + timedelta(seconds=10),
    )

    assert running.last_candle_close_at == candle_close_at
    assert errored.status is WorkerStatus.ERROR
    assert errored.health is WorkerHealth.ERROR
    assert errored.last_error == "broker disconnected"


def test_worker_registry_retains_bounded_event_history(worker_key: WorkerKey) -> None:
    """Event retention should keep the newest entries inside the cap."""

    registry = WorkerRegistry(heartbeat_ttl_s=60, max_events=3)
    start = datetime(2026, 4, 20, 14, 0, tzinfo=UTC)
    registry.register(worker_key, source="tradier", recorded_at=start)
    registry.mark_running(worker_key, recorded_at=start + timedelta(seconds=1))
    registry.mark_stopping(worker_key, recorded_at=start + timedelta(seconds=2))
    registry.mark_stopped(worker_key, recorded_at=start + timedelta(seconds=3))

    events = registry.list_events()
    assert len(events) == 3
    assert [event.status for event in events] == [
        WorkerStatus.RUNNING,
        WorkerStatus.STOPPING,
        WorkerStatus.STOPPED,
    ]
