"""Tests for Phase 5 crypto candle worker activation wiring."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.candle.crypto_scheduler import due_crypto_timeframes, next_crypto_candle_dispatch_at
from app.candle.kraken_rest import KrakenRestCandleSourceClient
from app.models.domain import Candle
from app.services.crypto_runtime_targets import CryptoRuntimeTarget
from app.workers.crypto_worker_sync import CryptoWorkerSynchronizer
from app.workers.worker_lifecycle import ManagedWorker, WorkerLifecycleManager
from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerKey


class _MarkerWorker:
    """Managed worker marker used to assert factory wiring."""

    def __init__(self) -> None:
        self.started = False

    async def run(self) -> None:
        self.started = True


@pytest.mark.asyncio
async def test_crypto_synchronizer_uses_real_managed_worker_factory() -> None:
    """Phase 5 sync should be able to launch candle-worker managed workers."""

    registry = WorkerRegistry(heartbeat_ttl_s=60)
    target = CryptoRuntimeTarget(
        key=WorkerKey(symbol="BTC/USD", asset_class="crypto", timeframe="1Day")
    )
    launched: list[str] = []

    def _factory(key: WorkerKey) -> ManagedWorker:
        launched.append(key.id)
        return _MarkerWorker()

    synchronizer = CryptoWorkerSynchronizer(
        lifecycle_manager=WorkerLifecycleManager(registry),
        registry=registry,
        target_provider=lambda: [target],
        managed_worker_factory=_factory,
    )

    result = await synchronizer.sync_crypto_targets()

    assert result.started == 1
    assert launched == ["crypto:BTC/USD:1Day"]


@pytest.mark.asyncio
async def test_kraken_rest_client_fetches_confirmed_candle() -> None:
    """Kraken REST client should convert OHLC payloads to domain candles."""

    async def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["pair"] == "XBTUSD"
        payload = {
            "error": [],
            "result": {
                "XXBTZUSD": [
                    [
                        1_776_000_000,
                        "50000.0",
                        "51000.0",
                        "49000.0",
                        "50500.0",
                        "50250.0",
                        "100.0",
                        10,
                    ],
                ],
                "last": "1776000000",
            },
        }
        return httpx.Response(200, content=json.dumps(payload).encode())

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = KrakenRestCandleSourceClient(client=http_client)
        candle = await client.fetch_confirmed_candle(
            "BTC/USD",
            "1Day",
            datetime(2026, 4, 23, tzinfo=UTC),
        )

    assert candle == Candle(
        time=datetime.fromtimestamp(1_776_000_000, tz=UTC),
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="1Day",
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0,
        source="kraken",
    )


def test_crypto_scheduler_calculates_due_timeframes_after_close_delay() -> None:
    """Scheduler should queue only timeframes that closed 20 seconds ago."""

    assert due_crypto_timeframes(
        datetime(2026, 4, 23, 9, 5, 20, tzinfo=UTC)
    ) == ["5m"]
    assert due_crypto_timeframes(datetime(2026, 4, 23, 9, 15, 20, tzinfo=UTC)) == [
        "5m",
        "15m",
    ]
    assert due_crypto_timeframes(datetime(2026, 4, 23, 10, 0, 20, tzinfo=UTC)) == [
        "5m",
        "15m",
        "1h",
    ]
    assert due_crypto_timeframes(datetime(2026, 4, 23, 12, 0, 20, tzinfo=UTC)) == [
        "5m",
        "15m",
        "1h",
        "4h",
    ]
    assert due_crypto_timeframes(datetime(2026, 4, 23, 12, 0, 19, tzinfo=UTC)) == []


def test_crypto_scheduler_calculates_next_dispatch_after_close_delay() -> None:
    """Scheduler should sleep until the next candle close plus 20 seconds."""

    assert next_crypto_candle_dispatch_at(
        datetime(2026, 4, 23, 9, 2, 0, tzinfo=UTC)
    ) == datetime(2026, 4, 23, 9, 5, 20, tzinfo=UTC)
    assert next_crypto_candle_dispatch_at(
        datetime(2026, 4, 23, 9, 5, 20, tzinfo=UTC)
    ) == datetime(2026, 4, 23, 9, 10, 20, tzinfo=UTC)
