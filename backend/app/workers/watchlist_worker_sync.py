"""Watchlist-driven worker reconciliation for Phase 4."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.workers.worker_lifecycle import (
    ManagedWorker,
    WorkerLaunchSpec,
    WorkerLifecycleManager,
    WorkerSyncResult,
)
from app.workers.worker_runtime_state import WorkerKey


class ActiveWatchlistRow(Protocol):
    """Minimal watchlist row contract needed for worker reconciliation."""

    symbol: str
    asset_class: str


class ActiveWatchlistRepository(Protocol):
    """Repository contract used by the watchlist worker synchronizer."""

    async def list_active(self) -> list[ActiveWatchlistRow]:
        """Return active watchlist rows."""


@dataclass(frozen=True, slots=True)
class WatchlistWorkerSyncConfig:
    """Configuration for stock watchlist worker synchronization."""

    timeframe: str
    source: str = "tradier"
    asset_class: str = "stock"


class WatchlistWorkerSynchronizer:
    """Sync stock candle workers so they follow the active watchlist."""

    def __init__(
        self,
        repository: ActiveWatchlistRepository,
        lifecycle_manager: WorkerLifecycleManager,
        worker_factory: Callable[[str, str], ManagedWorker],
        config: WatchlistWorkerSyncConfig,
    ) -> None:
        self._repository = repository
        self._lifecycle_manager = lifecycle_manager
        self._worker_factory = worker_factory
        self._config = config

    async def sync_active_watchlist(self) -> WorkerSyncResult:
        """Reconcile active workers against the current active stock watchlist."""

        rows = await self._repository.list_active()
        desired_specs = self.build_launch_specs(rows)
        return await self._lifecycle_manager.sync(desired_specs)

    def build_launch_specs(
        self,
        rows: Sequence[ActiveWatchlistRow],
    ) -> list[WorkerLaunchSpec]:
        """Build stable worker launch specs from active watchlist rows."""

        desired_symbols = {
            row.symbol.upper()
            for row in rows
            if row.asset_class.lower() == self._config.asset_class
        }
        return [self._build_launch_spec(symbol) for symbol in sorted(desired_symbols)]

    def _build_launch_spec(self, symbol: str) -> WorkerLaunchSpec:
        key = WorkerKey(
            symbol=symbol,
            asset_class=self._config.asset_class,
            timeframe=self._config.timeframe,
        )
        return WorkerLaunchSpec(
            key=key,
            source=self._config.source,
            worker_factory=self._make_worker_factory(symbol),
            task_name=f"worker:{key.id}",
        )

    def _make_worker_factory(self, symbol: str) -> Callable[[], ManagedWorker]:
        """Bind a symbol and timeframe into the managed worker factory."""

        def _factory() -> ManagedWorker:
            return self._worker_factory(symbol, self._config.timeframe)

        return _factory
