"""Tests for Phase 4 watchlist-driven worker synchronization."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.workers import (
    WatchlistWorkerSyncConfig,
    WatchlistWorkerSynchronizer,
    WorkerKey,
    WorkerLifecycleManager,
    WorkerRegistry,
    WorkerStatus,
)


class _BlockingWorker:
    """Worker that runs until cancelled by the lifecycle manager."""

    async def run(self) -> None:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise


@dataclass(frozen=True, slots=True)
class _WatchlistRow:
    """Minimal row used by synchronizer tests."""

    symbol: str
    asset_class: str


class _FakeWatchlistRepository:
    """In-memory repository for active watchlist rows."""

    def __init__(self, rows: list[_WatchlistRow]) -> None:
        self.rows = rows

    async def list_active(self) -> list[_WatchlistRow]:
        return list(self.rows)


@pytest.fixture
def registry() -> WorkerRegistry:
    """Return a registry configured for watchlist sync tests."""

    return WorkerRegistry(heartbeat_ttl_s=60)


@pytest.mark.asyncio
async def test_watchlist_synchronizer_builds_stock_specs_only() -> None:
    """Only active stock symbols should become desired worker specs."""

    repository = _FakeWatchlistRepository(
        [
            _WatchlistRow(symbol="msft", asset_class="stock"),
            _WatchlistRow(symbol="BTC/USD", asset_class="crypto"),
            _WatchlistRow(symbol="AAPL", asset_class="stock"),
            _WatchlistRow(symbol="MSFT", asset_class="stock"),
        ]
    )
    synchronizer = WatchlistWorkerSynchronizer(
        repository=repository,
        lifecycle_manager=WorkerLifecycleManager(WorkerRegistry()),
        worker_factory=lambda symbol, timeframe: _BlockingWorker(),
        config=WatchlistWorkerSyncConfig(timeframe="1Day"),
    )

    specs = synchronizer.build_launch_specs(await repository.list_active())

    assert [spec.key.id for spec in specs] == [
        "stock:AAPL:1Day",
        "stock:MSFT:1Day",
    ]
    assert all(spec.source == "tradier" for spec in specs)


@pytest.mark.asyncio
async def test_watchlist_synchronizer_attaches_and_detaches_workers(
    registry: WorkerRegistry,
) -> None:
    """Syncing the watchlist should start new stock workers and stop removed ones."""

    repository = _FakeWatchlistRepository(
        [
            _WatchlistRow(symbol="AAPL", asset_class="stock"),
            _WatchlistRow(symbol="MSFT", asset_class="stock"),
        ]
    )
    manager = WorkerLifecycleManager(registry)
    synchronizer = WatchlistWorkerSynchronizer(
        repository=repository,
        lifecycle_manager=manager,
        worker_factory=lambda symbol, timeframe: _BlockingWorker(),
        config=WatchlistWorkerSyncConfig(timeframe="1Day"),
    )

    first = await synchronizer.sync_active_watchlist()
    repository.rows = [
        _WatchlistRow(symbol="MSFT", asset_class="stock"),
        _WatchlistRow(symbol="TSLA", asset_class="stock"),
    ]
    second = await synchronizer.sync_active_watchlist()
    await asyncio.sleep(0)

    assert first.started == 2
    assert first.stopped == 0
    assert first.unchanged == 0
    assert second.started == 1
    assert second.stopped == 1
    assert second.unchanged == 1
    assert manager.active_worker_ids == {"stock:MSFT:1Day", "stock:TSLA:1Day"}

    removed_snapshot = registry.get(
        WorkerKey(symbol="AAPL", asset_class="stock", timeframe="1Day")
    )
    assert removed_snapshot is not None
    assert removed_snapshot.status is WorkerStatus.STOPPED

    await manager.shutdown_all()
