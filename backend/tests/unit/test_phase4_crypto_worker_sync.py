"""Tests for crypto runtime worker attachment synchronization."""

from __future__ import annotations

import asyncio

import pytest

from app.services.crypto_runtime_targets import CryptoRuntimeTarget
from app.workers.crypto_worker_sync import (
    CryptoWorkerSyncConfig,
    CryptoWorkerSynchronizer,
)
from app.workers.worker_lifecycle import WorkerLifecycleManager
from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerHealth, WorkerKey, WorkerStatus


@pytest.mark.asyncio
async def test_crypto_worker_synchronizer_builds_one_spec_per_target() -> None:
    """Crypto target sync should dedupe launch specs by worker identity."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    target = CryptoRuntimeTarget(
        key=WorkerKey(symbol="BTC/USD", asset_class="crypto", timeframe="1Day")
    )
    synchronizer = CryptoWorkerSynchronizer(
        lifecycle_manager=WorkerLifecycleManager(registry),
        registry=registry,
        target_provider=lambda: [target, target],
    )

    specs = synchronizer.build_launch_specs([target, target])

    assert [spec.key.id for spec in specs] == ["crypto:BTC/USD:1Day"]
    assert specs[0].source == "crypto scope target derivation"
    assert specs[0].task_name == "worker:crypto:BTC/USD:1Day"


@pytest.mark.asyncio
async def test_crypto_worker_synchronizer_attaches_and_detaches_targets() -> None:
    """Syncing crypto targets should start new workers and stop removed ones."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    manager = WorkerLifecycleManager(registry)
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
    )

    first = await synchronizer.sync_crypto_targets()
    await asyncio.sleep(0.02)
    targets = [eth, sol]
    second = await synchronizer.sync_crypto_targets()
    await asyncio.sleep(0.02)

    assert first.started == 2
    assert first.stopped == 0
    assert first.unchanged == 0
    assert second.started == 1
    assert second.stopped == 1
    assert second.unchanged == 1
    assert manager.active_worker_ids == {"crypto:ETH/USD:1Day", "crypto:SOL/USD:1Day"}

    stopped_snapshot = registry.get(btc.key)
    assert stopped_snapshot is not None
    assert stopped_snapshot.status is WorkerStatus.STOPPED

    active_snapshot = registry.get(eth.key)
    assert active_snapshot is not None
    assert active_snapshot.status is WorkerStatus.RUNNING
    assert active_snapshot.health is WorkerHealth.HEALTHY
    assert active_snapshot.last_heartbeat_at is not None

    await manager.shutdown_all()
