"""Crypto runtime target worker attachment for scope-derived targets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.services.crypto_runtime_targets import (
    CRYPTO_TARGET_SOURCE,
    CryptoRuntimeTarget,
    list_crypto_runtime_targets,
)
from app.workers.worker_lifecycle import (
    ManagedWorker,
    WorkerLaunchSpec,
    WorkerLifecycleManager,
    WorkerSyncResult,
)
from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerKey

CRYPTO_ATTACHMENT_HEARTBEAT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class CryptoWorkerSyncConfig:
    """Configuration for crypto target worker synchronization."""

    source: str = CRYPTO_TARGET_SOURCE
    heartbeat_seconds: float = CRYPTO_ATTACHMENT_HEARTBEAT_SECONDS


class CryptoScopeHeartbeatWorker:
    """Lightweight attached worker used before candle fetching is enabled.

    This worker proves that a crypto runtime target is attached and supervised.
    It deliberately does not fetch candles yet; Phase 5 replaces this heartbeat
    worker with the real Kraken candle worker path.
    """

    def __init__(
        self,
        *,
        registry: WorkerRegistry,
        key: WorkerKey,
        heartbeat_seconds: float,
    ) -> None:
        self._registry = registry
        self._key = key
        self._heartbeat_seconds = heartbeat_seconds

    async def run(self) -> None:
        """Emit heartbeats until the lifecycle manager cancels the worker."""

        try:
            while True:
                self._registry.mark_heartbeat(self._key)
                await asyncio.sleep(self._heartbeat_seconds)
        except asyncio.CancelledError:
            raise


class CryptoWorkerSynchronizer:
    """Sync attached crypto workers so they follow derived runtime targets."""

    def __init__(
        self,
        *,
        lifecycle_manager: WorkerLifecycleManager,
        registry: WorkerRegistry,
        target_provider: Callable[[], list[CryptoRuntimeTarget]] = list_crypto_runtime_targets,
        config: CryptoWorkerSyncConfig | None = None,
    ) -> None:
        self._lifecycle_manager = lifecycle_manager
        self._registry = registry
        self._target_provider = target_provider
        self._config = config or CryptoWorkerSyncConfig()

    async def sync_crypto_targets(self) -> WorkerSyncResult:
        """Reconcile attached workers against the current crypto target set."""

        desired_specs = self.build_launch_specs(self._target_provider())
        return await self._lifecycle_manager.sync(desired_specs)

    def build_launch_specs(
        self,
        targets: Sequence[CryptoRuntimeTarget],
    ) -> list[WorkerLaunchSpec]:
        """Build one stable worker launch spec per crypto symbol/timeframe."""

        unique_targets = {target.key.id: target for target in targets}
        return [
            self._build_launch_spec(unique_targets[worker_id])
            for worker_id in sorted(unique_targets)
        ]

    def _build_launch_spec(self, target: CryptoRuntimeTarget) -> WorkerLaunchSpec:
        return WorkerLaunchSpec(
            key=target.key,
            source=self._config.source,
            worker_factory=self._make_worker_factory(target.key),
            task_name=f"worker:{target.key.id}",
        )

    def _make_worker_factory(self, key: WorkerKey) -> Callable[[], ManagedWorker]:
        """Bind a crypto worker key into a managed heartbeat worker factory."""

        def _factory() -> ManagedWorker:
            return CryptoScopeHeartbeatWorker(
                registry=self._registry,
                key=key,
                heartbeat_seconds=self._config.heartbeat_seconds,
            )

        return _factory
