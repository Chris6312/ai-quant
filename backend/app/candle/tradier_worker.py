"""Tradier candle worker implementations and watchlist supervision."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.candle.worker import CandleWorker, RedisClient
from app.config.constants import DEFAULT_CANDLE_SOURCE
from app.models.domain import Candle
from app.repositories.candles import CandleRepository


class TradierMarketDataClient(Protocol):
    """Define the Tradier market-data contract."""

    async def stream_candle_closes(self, symbol: str, timeframe: str) -> AsyncIterator[datetime]:
        """Yield Tradier candle close timestamps."""

    async def fetch_confirmed_candle(
        self,
        symbol: str,
        timeframe: str,
        close_time: datetime,
    ) -> Candle:
        """Fetch a confirmed Tradier candle."""


class TradierCandleWorker(CandleWorker):
    """Live candle worker for stock watchlist symbols."""

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        repository: CandleRepository,
        redis_client: RedisClient,
        client: TradierMarketDataClient,
        delay_s: int = 17,
    ) -> None:
        super().__init__(
            symbol=symbol,
            asset_class="stock",
            timeframe=timeframe,
            source=DEFAULT_CANDLE_SOURCE,
            repository=repository,
            redis_client=redis_client,
            client=client,
            delay_s=delay_s,
        )
        self._tradier_client = client

    async def _stream_candle_closes(self) -> AsyncIterator[datetime]:
        async for candle_close_ts in self._tradier_client.stream_candle_closes(
            self.symbol,
            self.timeframe,
        ):
            yield candle_close_ts

    async def _fetch_confirmed_candle(self, candle_close_ts: datetime) -> Candle:
        return await self._tradier_client.fetch_confirmed_candle(
            self.symbol,
            self.timeframe,
            candle_close_ts,
        )


@dataclass(slots=True)
class ActiveWorkerHandle:
    """Track an active worker task and its worker instance."""

    worker: TradierCandleWorker
    task: asyncio.Task[None]


class TradierWorkerManager:
    """Start and stop stock candle workers as the watchlist changes."""

    def __init__(
        self,
        worker_factory: Callable[[str, str], TradierCandleWorker],
        timeframe: str,
    ) -> None:
        self.worker_factory = worker_factory
        self.timeframe = timeframe
        self._active: dict[str, ActiveWorkerHandle] = {}

    @property
    def active_symbols(self) -> set[str]:
        """Return active managed symbols."""

        return set(self._active)

    async def sync_symbols(self, symbols: Sequence[str]) -> None:
        """Ensure only the requested symbols have live workers."""

        desired = {symbol.upper() for symbol in symbols}
        current = set(self._active)
        for symbol in current - desired:
            await self.stop_symbol(symbol)
        for symbol in desired - current:
            await self.start_symbol(symbol)

    async def start_symbol(self, symbol: str) -> None:
        """Create and start a worker for one symbol."""

        if symbol in self._active:
            return
        worker = self.worker_factory(symbol, self.timeframe)
        task = asyncio.create_task(worker.run())
        self._active[symbol] = ActiveWorkerHandle(worker=worker, task=task)

    async def stop_symbol(self, symbol: str) -> None:
        """Cancel the active worker for one symbol."""

        handle = self._active.pop(symbol, None)
        if handle is None:
            return
        handle.task.cancel()
        with suppress(asyncio.CancelledError):
            await handle.task

    async def handle_watchlist_updated(self, payload: Mapping[str, Sequence[str]]) -> None:
        """React to a Redis watchlist-updated payload."""

        added = payload.get("added", [])
        removed = payload.get("removed", [])
        for symbol in added:
            await self.start_symbol(symbol)
        for symbol in removed:
            await self.stop_symbol(symbol)
