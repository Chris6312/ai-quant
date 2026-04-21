"""Tests for the Phase 4 worker lifecycle manager."""

from __future__ import annotations

import asyncio

import pytest

from app.workers import WorkerKey, WorkerRegistry, WorkerStatus
from app.workers.worker_lifecycle import WorkerLaunchSpec, WorkerLifecycleManager


class _BlockingWorker:
    """Worker that runs until explicitly cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self) -> None:
        self.started.set()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise


class _FailingWorker:
    """Worker that fails immediately after starting."""

    async def run(self) -> None:
        raise RuntimeError("feed disconnected")


@pytest.fixture
def registry() -> WorkerRegistry:
    """Return a registry configured for lifecycle tests."""

    return WorkerRegistry(heartbeat_ttl_s=60)


@pytest.fixture
def worker_key() -> WorkerKey:
    """Return a stock worker key used in lifecycle tests."""

    return WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")


@pytest.mark.asyncio
async def test_lifecycle_manager_starts_worker_and_registers_task(
    registry: WorkerRegistry,
    worker_key: WorkerKey,
) -> None:
    """Starting a worker should create a task and mark it running."""

    worker = _BlockingWorker()
    manager = WorkerLifecycleManager(registry)

    snapshot = await manager.start(
        WorkerLaunchSpec(
            key=worker_key,
            source="tradier",
            worker_factory=lambda: worker,
        )
    )
    await worker.started.wait()

    assert snapshot.status is WorkerStatus.RUNNING
    assert manager.active_worker_ids == {worker_key.id}
    task = manager.get_task(worker_key)
    assert task is not None
    assert registry.get_task_ref(worker_key) is task

    await manager.shutdown_all()


@pytest.mark.asyncio
async def test_lifecycle_manager_syncs_desired_worker_set(
    registry: WorkerRegistry,
) -> None:
    """Reconciling desired workers should start new tasks and stop removed ones."""

    manager = WorkerLifecycleManager(registry)
    aapl_key = WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")
    msft_key = WorkerKey(symbol="MSFT", asset_class="stock", timeframe="1Day")
    tsla_key = WorkerKey(symbol="TSLA", asset_class="stock", timeframe="1Day")

    first = await manager.sync(
        [
            WorkerLaunchSpec(
                key=aapl_key,
                source="tradier",
                worker_factory=_BlockingWorker,
            ),
            WorkerLaunchSpec(
                key=msft_key,
                source="tradier",
                worker_factory=_BlockingWorker,
            ),
        ]
    )
    second = await manager.sync(
        [
            WorkerLaunchSpec(
                key=msft_key,
                source="tradier",
                worker_factory=_BlockingWorker,
            ),
            WorkerLaunchSpec(
                key=tsla_key,
                source="tradier",
                worker_factory=_BlockingWorker,
            ),
        ]
    )
    await asyncio.sleep(0)

    assert first.started == 2
    assert first.stopped == 0
    assert first.unchanged == 0
    assert second.started == 1
    assert second.stopped == 1
    assert second.unchanged == 1
    assert manager.active_worker_ids == {msft_key.id, tsla_key.id}
    stale_snapshot = registry.get(aapl_key)
    assert stale_snapshot is not None
    assert stale_snapshot.status is WorkerStatus.STOPPED

    await manager.shutdown_all()


@pytest.mark.asyncio
async def test_lifecycle_manager_marks_crashed_worker_as_error(
    registry: WorkerRegistry,
    worker_key: WorkerKey,
) -> None:
    """A task failure should move the registry snapshot into error state."""

    manager = WorkerLifecycleManager(registry)
    await manager.start(
        WorkerLaunchSpec(
            key=worker_key,
            source="tradier",
            worker_factory=_FailingWorker,
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    snapshot = registry.get(worker_key)
    assert snapshot is not None
    assert snapshot.status is WorkerStatus.ERROR
    assert snapshot.last_error == "feed disconnected"
    assert manager.active_worker_ids == set()


@pytest.mark.asyncio
async def test_lifecycle_manager_shutdown_stops_everything(
    registry: WorkerRegistry,
) -> None:
    """Shutdown should stop all active workers and leave stopped snapshots behind."""

    manager = WorkerLifecycleManager(registry)
    aapl_key = WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")
    msft_key = WorkerKey(symbol="MSFT", asset_class="stock", timeframe="1Day")

    await manager.start(
        WorkerLaunchSpec(
            key=aapl_key,
            source="tradier",
            worker_factory=_BlockingWorker,
        )
    )
    await manager.start(
        WorkerLaunchSpec(
            key=msft_key,
            source="tradier",
            worker_factory=_BlockingWorker,
        )
    )

    snapshots = await manager.shutdown_all()

    assert len(snapshots) == 2
    assert manager.active_worker_ids == set()
    assert registry.get(aapl_key) is not None
    assert registry.get(aapl_key).status is WorkerStatus.STOPPED
    assert registry.get(msft_key) is not None
    assert registry.get(msft_key).status is WorkerStatus.STOPPED
