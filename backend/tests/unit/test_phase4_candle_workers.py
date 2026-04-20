"""Tests for Phase 4 market-data workers and backfill services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.candle.backfill import BackfillService
from app.candle.kraken_worker import KRAKEN_UNIVERSE, KrakenUniverseSupervisor
from app.candle.tradier_worker import TradierWorkerManager
from app.candle.worker import CandleWorker
from app.models.domain import Candle


class _FakeRedis:
    """Stand in for an async Redis client."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.messages: list[tuple[str, str]] = []

    async def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
        keepttl: bool = False,
        get: bool = False,
    ) -> bool:
        """Store the key and emulate NX semantics."""

        if nx and name in self.keys:
            return False
        self.keys[name] = value
        if ex is not None:
            self.expirations[name] = ex
        return True

    async def expire(self, name: str, time: int) -> bool:
        """Store the expiration value."""

        self.expirations[name] = time
        return True

    async def publish(self, channel: str, message: str) -> int:
        """Capture published messages."""

        self.messages.append((channel, message))
        return 1


class _FakeRepository:
    """Stand in for the candle repository."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    async def bulk_upsert(self, rows: list[object]) -> None:
        """Capture rows written by the worker or backfill service."""

        self.rows.extend(rows)


class _FakeSourceClient:
    """Stand in for a live or historical market-data client."""

    def __init__(self, candle: Candle) -> None:
        self.candle = candle
        self.stream_count = 0
        self.fetch_count = 0

    async def stream_candle_closes(
        self,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[datetime]:
        """Yield one candle close then stop."""

        self.stream_count += 1
        yield self.candle.time

    async def fetch_confirmed_candle(
        self,
        symbol: str,
        timeframe: str,
        close_time: datetime,
    ) -> Candle:
        """Return the configured candle."""

        self.fetch_count += 1
        return self.candle

    async def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Return one historical candle."""

        return [self.candle]


class _TestWorker(CandleWorker):
    """Minimal worker implementation for unit tests."""

    async def _stream_candle_closes(self) -> AsyncIterator[datetime]:
        if False:
            yield datetime.now(tz=UTC)

    async def _fetch_confirmed_candle(self, candle_close_ts: datetime) -> Candle:
        return self.client.candle


@pytest.mark.asyncio
async def test_candle_worker_processes_close_and_publishes() -> None:
    """A candle close should be validated, persisted, and published."""

    candle = Candle(
        time=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        symbol="AAPL",
        asset_class="stock",
        timeframe="1Day",
        open=100.0,
        high=102.0,
        low=99.5,
        close=101.0,
        volume=1_000.0,
        source="tradier",
    )
    repository = _FakeRepository()
    redis_client = _FakeRedis()
    source_client = _FakeSourceClient(candle)
    worker = _TestWorker(
        symbol="AAPL",
        asset_class="stock",
        timeframe="1Day",
        source="tradier",
        repository=repository,
        redis_client=redis_client,
        client=source_client,
        delay_s=0,
    )

    result = await worker.process_candle_close(candle.time)

    assert result == candle
    assert len(repository.rows) == 1
    assert repository.rows[0].source == "tradier"
    assert redis_client.messages[0][0] == "candle_closed:stock:AAPL:1Day"
    assert "\"symbol\":\"AAPL\"" in redis_client.messages[0][1]


@pytest.mark.asyncio
async def test_tradier_worker_manager_syncs_symbol_set() -> None:
    """The Tradier manager should start and stop workers to match the watchlist."""

    started: list[str] = []

    async def _noop() -> None:
        return None

    def _factory(symbol: str, timeframe: str) -> SimpleNamespace:
        started.append(symbol)
        return SimpleNamespace(run=_noop)

    manager = TradierWorkerManager(worker_factory=_factory, timeframe="1Day")
    await manager.sync_symbols(["AAPL", "MSFT"])
    assert manager.active_symbols == {"AAPL", "MSFT"}
    await manager.sync_symbols(["AAPL"])
    assert manager.active_symbols == {"AAPL"}
    assert set(started) == {"AAPL", "MSFT"}


def test_kraken_universe_supervisor_builds_fixed_universe_workers() -> None:
    """The Kraken supervisor should always cover the 15 fixed pairs."""

    supervisor = KrakenUniverseSupervisor(
        timeframe="1Hour",
        worker_factory=lambda symbol, timeframe: SimpleNamespace(
            symbol=symbol,
            timeframe=timeframe,
        ),
    )
    workers = supervisor.build_workers()
    assert len(workers) == len(KRAKEN_UNIVERSE)
    assert {worker.symbol for worker in workers} == set(KRAKEN_UNIVERSE)


@pytest.mark.asyncio
async def test_backfill_service_persists_history() -> None:
    """Backfill should persist validated historical candles."""

    candle = Candle(
        time=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        symbol="AAPL",
        asset_class="stock",
        timeframe="1Day",
        open=100.0,
        high=102.0,
        low=99.5,
        close=101.0,
        volume=1_000.0,
        source="tradier",
    )
    repository = _FakeRepository()
    service = BackfillService(repository)
    total = await service.backfill_symbol(
        symbol="AAPL",
        asset_class="stock",
        timeframe="1Day",
        client=_FakeSourceClient(candle),
        source="tradier",
        lookback_days=7,
    )
    assert total == 1
    assert len(repository.rows) == 1
    assert repository.rows[0].source == "tradier"
