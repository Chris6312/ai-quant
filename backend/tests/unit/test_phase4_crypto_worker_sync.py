"""Tests for crypto runtime candle scheduler synchronization."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from app.services.crypto_runtime_targets import CryptoRuntimeTarget
from app.workers.crypto_worker_sync import (
    CRYPTO_CANDLE_SCHEDULER_SOURCE,
    CRYPTO_CANDLE_SCHEDULER_SYMBOL,
    CRYPTO_CANDLE_SCHEDULER_TIMEFRAME,
    CryptoWorkerSyncConfig,
    CryptoWorkerSynchronizer,
)
from app.workers.worker_lifecycle import WorkerLifecycleManager
from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerHealth, WorkerKey, WorkerStatus


@dataclass(slots=True)
class _FakeDispatcher:
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def send_task(self, name: str, kwargs: dict[str, object]) -> object:
        self.calls.append((name, kwargs))
        return {"task": name}


@pytest.mark.asyncio
async def test_crypto_worker_synchronizer_builds_one_scheduler_spec() -> None:
    """Crypto sync should build one scheduler spec for the whole target set."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    target = CryptoRuntimeTarget(
        key=WorkerKey(symbol="BTC/USD", asset_class="crypto", timeframe="1Day")
    )
    synchronizer = CryptoWorkerSynchronizer(
        lifecycle_manager=WorkerLifecycleManager(registry),
        registry=registry,
        target_provider=lambda: [target, target],
        dispatcher=_FakeDispatcher(),
    )

    specs = synchronizer.build_launch_specs([target, target])

    assert [spec.key.id for spec in specs] == [
        f"crypto:{CRYPTO_CANDLE_SCHEDULER_SYMBOL}:{CRYPTO_CANDLE_SCHEDULER_TIMEFRAME}"
    ]
    assert specs[0].source == CRYPTO_CANDLE_SCHEDULER_SOURCE
    assert specs[0].task_name == (
        f"worker:crypto:{CRYPTO_CANDLE_SCHEDULER_SYMBOL}:{CRYPTO_CANDLE_SCHEDULER_TIMEFRAME}"
    )


@pytest.mark.asyncio
async def test_crypto_worker_synchronizer_keeps_one_scheduler_for_target_changes() -> None:
    """Target symbol changes should not create one task per symbol."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    manager = WorkerLifecycleManager(registry)
    dispatcher = _FakeDispatcher()
    btc = CryptoRuntimeTarget(
        key=WorkerKey(symbol="BTC/USD", asset_class="crypto", timeframe="1Day")
    )
    eth = CryptoRuntimeTarget(
        key=WorkerKey(symbol="ETH/USD", asset_class="crypto", timeframe="1Day")
    )
    sol = CryptoRuntimeTarget(
        key=WorkerKey(symbol="SOL/USD", asset_class="crypto", timeframe="1Day")
    )
    targets = [btc, eth]
    synchronizer = CryptoWorkerSynchronizer(
        lifecycle_manager=manager,
        registry=registry,
        target_provider=lambda: list(targets),
        config=CryptoWorkerSyncConfig(heartbeat_seconds=0.01),
        dispatcher=dispatcher,
    )

    first = await synchronizer.sync_crypto_targets()
    await asyncio.sleep(0.02)
    targets = [eth, sol]
    second = await synchronizer.sync_crypto_targets()
    await asyncio.sleep(0.02)

    scheduler_id = f"crypto:{CRYPTO_CANDLE_SCHEDULER_SYMBOL}:{CRYPTO_CANDLE_SCHEDULER_TIMEFRAME}"
    assert first.started == 1
    assert first.stopped == 0
    assert first.unchanged == 0
    assert second.started == 0
    assert second.stopped == 0
    assert second.unchanged == 1
    assert manager.active_worker_ids == {scheduler_id}
    assert dispatcher.calls

    scheduler_key = WorkerKey(
        symbol=CRYPTO_CANDLE_SCHEDULER_SYMBOL,
        asset_class="crypto",
        timeframe=CRYPTO_CANDLE_SCHEDULER_TIMEFRAME,
    )
    active_snapshot = registry.get(scheduler_key)
    assert active_snapshot is not None
    assert active_snapshot.status is WorkerStatus.RUNNING
    assert active_snapshot.health is WorkerHealth.HEALTHY
    assert active_snapshot.last_heartbeat_at is not None

    await manager.shutdown_all()
