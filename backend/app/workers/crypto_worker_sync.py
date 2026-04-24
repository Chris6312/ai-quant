"""Crypto candle scheduler attachment for scope-derived targets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.candle.crypto_scheduler import (
    get_pending_strategy_timeframes,
    latest_crypto_close_id,
    next_crypto_candle_dispatch_at,
)
from app.services.crypto_runtime_targets import (
    CryptoRuntimeTarget,
    list_crypto_runtime_targets,
)
from app.tasks.crypto_candles import (
    build_crypto_initial_backfill_payload,
    build_crypto_sync_task_payload,
)
from app.tasks.worker import celery_app
from app.workers.worker_lifecycle import (
    ManagedWorker,
    WorkerLaunchSpec,
    WorkerLifecycleManager,
    WorkerSyncResult,
)
from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerKey

CRYPTO_SCHEDULER_HEARTBEAT_SECONDS = 30.0
CRYPTO_CANDLE_SCHEDULER_SYMBOL = "KRAKEN_UNIVERSE"
CRYPTO_CANDLE_SCHEDULER_TIMEFRAME = "multi"
CRYPTO_CANDLE_SCHEDULER_SOURCE = "kraken crypto candle scheduler"
CRYPTO_LEGACY_TARGET_SOURCE = "crypto scope target derivation"


class CeleryTaskDispatcher(Protocol):
    """Minimal task-dispatch protocol used by the scheduler worker."""

    def send_task(self, name: str, kwargs: dict[str, object]) -> object:
        """Submit a task by name."""


class CeleryAppTaskDispatcher:
    """Typed adapter around Celery's broad send_task signature."""

    def send_task(self, name: str, kwargs: dict[str, object]) -> object:
        """Submit a Celery task by name with keyword arguments."""

        return celery_app.send_task(name, kwargs=kwargs)


@dataclass(frozen=True, slots=True)
class CryptoWorkerSyncConfig:
    """Configuration for crypto candle scheduler synchronization."""

    source: str = CRYPTO_CANDLE_SCHEDULER_SOURCE
    heartbeat_seconds: float = CRYPTO_SCHEDULER_HEARTBEAT_SECONDS


class CeleryCryptoCandleSchedulerWorker:
    """Single runtime worker that schedules crypto candle work through Celery.

    The runtime process owns only one lightweight scheduler worker. Celery owns
    the expensive Kraken backfill and incremental candle-sync jobs so the API
    event loop does not become the candle fetcher.
    """

    def __init__(
        self,
        *,
        registry: WorkerRegistry,
        key: WorkerKey,
        target_symbols: Sequence[str],
        heartbeat_seconds: float,
        dispatcher: CeleryTaskDispatcher | None = None,
    ) -> None:
        self._registry = registry
        self._key = key
        self._target_symbols = list(target_symbols)
        self._heartbeat_seconds = heartbeat_seconds
        self._dispatcher = dispatcher or CeleryAppTaskDispatcher()
        self._initial_backfill_dispatched = False
        self._last_sync_close_ids: dict[str, str] = {}

    async def run(self) -> None:
        """Emit heartbeats and submit Celery candle tasks until cancelled."""

        while True:
            self._registry.mark_heartbeat(self._key)
            await self._dispatch_candle_tasks(datetime.now(UTC))
            sleep_seconds = self._next_sleep_seconds()
            await asyncio.sleep(min(self._heartbeat_seconds, sleep_seconds))

    async def _dispatch_candle_tasks(self, now: datetime) -> None:
        if not self._initial_backfill_dispatched:
            initial_backfill = build_crypto_initial_backfill_payload(self._target_symbols)
            self._dispatcher.send_task(
                initial_backfill.name,
                kwargs=initial_backfill.kwargs,
            )
            self._initial_backfill_dispatched = True

        due = get_pending_strategy_timeframes(now, self._last_sync_close_ids)
        if due is None:
            return

        sync_payload = build_crypto_sync_task_payload(
            symbols=self._target_symbols,
            timeframes=due.timeframes,
        )
        now_utc = now.astimezone(UTC)
        sync_payload.kwargs["requested_at"] = now_utc.isoformat()
        sync_payload.kwargs["candle_close_at"] = due.close_at.isoformat()
        self._dispatcher.send_task(
            sync_payload.name,
            kwargs=sync_payload.kwargs,
        )
        timeframes_label = "/".join(due.timeframes)
        self._registry.mark_candle_close(
            self._key,
            due.close_at,
            recorded_at=now_utc,
            detail=(
                f"current candles dispatched for {timeframes_label} "
                f"close {due.close_at.isoformat()}"
            ),
        )

        for timeframe in due.timeframes:
            close_id = latest_crypto_close_id(now_utc, timeframe)
            if close_id is not None:
                self._last_sync_close_ids[timeframe] = close_id

    def _next_sleep_seconds(self) -> float:
        now = datetime.now(UTC)
        return max(0.0, (next_crypto_candle_dispatch_at(now) - now).total_seconds())


class CryptoWorkerSynchronizer:
    """Sync one crypto candle scheduler against the current target universe."""

    def __init__(
        self,
        *,
        lifecycle_manager: WorkerLifecycleManager,
        registry: WorkerRegistry,
        target_provider: Callable[[], list[CryptoRuntimeTarget]] = list_crypto_runtime_targets,
        config: CryptoWorkerSyncConfig | None = None,
        dispatcher: CeleryTaskDispatcher | None = None,
        managed_worker_factory: Callable[[WorkerKey], ManagedWorker] | None = None,
    ) -> None:
        self._lifecycle_manager = lifecycle_manager
        self._registry = registry
        self._target_provider = target_provider
        self._config = config or CryptoWorkerSyncConfig()
        self._dispatcher = dispatcher or CeleryAppTaskDispatcher()
        self._managed_worker_factory = managed_worker_factory

    async def sync_crypto_targets(self) -> WorkerSyncResult:
        """Reconcile crypto workers against the current target set."""

        desired_specs = self.build_launch_specs(self._target_provider())
        return await self._lifecycle_manager.sync(desired_specs)

    def build_launch_specs(
        self,
        targets: Sequence[CryptoRuntimeTarget],
    ) -> list[WorkerLaunchSpec]:
        """Build launch specs for crypto runtime candle scheduling.

        Normal Phase 5 behavior is one scheduler for the full crypto target set.
        The optional managed_worker_factory path preserves the older test and
        extension contract for callers that explicitly inject a worker per key.
        """

        if self._managed_worker_factory is not None:
            return self._build_legacy_target_specs(targets)

        target_symbols = sorted({target.key.symbol for target in targets})
        if not target_symbols:
            return []
        scheduler_key = WorkerKey(
            symbol=CRYPTO_CANDLE_SCHEDULER_SYMBOL,
            asset_class="crypto",
            timeframe=CRYPTO_CANDLE_SCHEDULER_TIMEFRAME,
        )
        return [
            WorkerLaunchSpec(
                key=scheduler_key,
                source=self._config.source,
                worker_factory=self._make_scheduler_worker_factory(
                    scheduler_key,
                    target_symbols,
                ),
                task_name=f"worker:{scheduler_key.id}",
            )
        ]

    def _build_legacy_target_specs(
        self,
        targets: Sequence[CryptoRuntimeTarget],
    ) -> list[WorkerLaunchSpec]:
        seen: set[str] = set()
        specs: list[WorkerLaunchSpec] = []
        for target in targets:
            key = target.key
            if key.id in seen:
                continue
            seen.add(key.id)
            specs.append(
                WorkerLaunchSpec(
                    key=key,
                    source=CRYPTO_LEGACY_TARGET_SOURCE,
                    worker_factory=self._make_legacy_worker_factory(key),
                    task_name=f"worker:{key.id}",
                )
            )
        return specs

    def _make_legacy_worker_factory(self, key: WorkerKey) -> Callable[[], ManagedWorker]:
        def _factory() -> ManagedWorker:
            if self._managed_worker_factory is None:
                raise RuntimeError("Managed worker factory is not configured")
            return self._managed_worker_factory(key)

        return _factory

    def _make_scheduler_worker_factory(
        self,
        key: WorkerKey,
        target_symbols: Sequence[str],
    ) -> Callable[[], ManagedWorker]:
        """Bind scheduler state into a managed worker factory."""

        def _factory() -> ManagedWorker:
            return CeleryCryptoCandleSchedulerWorker(
                registry=self._registry,
                key=key,
                target_symbols=target_symbols,
                heartbeat_seconds=self._config.heartbeat_seconds,
                dispatcher=self._dispatcher,
            )

        return _factory


__all__ = [
    "CRYPTO_CANDLE_SCHEDULER_SOURCE",
    "CRYPTO_CANDLE_SCHEDULER_SYMBOL",
    "CRYPTO_CANDLE_SCHEDULER_TIMEFRAME",
    "CRYPTO_LEGACY_TARGET_SOURCE",
    "CeleryAppTaskDispatcher",
    "CeleryCryptoCandleSchedulerWorker",
    "CeleryTaskDispatcher",
    "CryptoWorkerSyncConfig",
    "CryptoWorkerSynchronizer",
]
