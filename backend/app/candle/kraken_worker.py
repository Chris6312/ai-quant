"""Kraken candle workers for the fixed crypto universe."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.candle.worker import CandleWorker, RedisClient
from app.models.domain import Candle
from app.repositories.candles import CandleRepository

KRAKEN_UNIVERSE: tuple[str, ...] = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "LTC/USD",
    "BCH/USD",
    "LINK/USD",
    "UNI/USD",
    "AVAX/USD",
    "DOGE/USD",
    "DOT/USD",
    "AAVE/USD",
    "CRV/USD",
    "SUSHI/USD",
    "SHIB/USD",
    "XTZ/USD",
)

__all__ = ["KRAKEN_UNIVERSE", "KrakenCandleWorker", "KrakenUniverseSupervisor"]


class KrakenMarketDataClient(Protocol):
    """Define the Kraken market-data contract."""

    def stream_candle_closes(self, symbol: str, timeframe: str) -> AsyncIterator[datetime]:
        """Yield Kraken candle close timestamps."""

    async def fetch_confirmed_candle(
        self,
        symbol: str,
        timeframe: str,
        close_time: datetime,
    ) -> Candle:
        """Fetch a confirmed Kraken candle."""


class KrakenCandleWorker(CandleWorker):
    """Live candle worker for a fixed Kraken universe symbol."""

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        repository: CandleRepository,
        redis_client: RedisClient,
        client: KrakenMarketDataClient,
        delay_s: int = 17,
    ) -> None:
        super().__init__(
            symbol=symbol,
            asset_class="crypto",
            timeframe=timeframe,
            source="kraken",
            repository=repository,
            redis_client=redis_client,
            client=client,
            delay_s=delay_s,
        )
        self._kraken_client = client

    async def _stream_candle_closes(self) -> AsyncIterator[datetime]:
        async for candle_close_ts in self._kraken_client.stream_candle_closes(
            self.symbol,
            self.timeframe,
        ):
            yield candle_close_ts

    async def _fetch_confirmed_candle(self, candle_close_ts: datetime) -> Candle:
        return await self._kraken_client.fetch_confirmed_candle(
            self.symbol,
            self.timeframe,
            candle_close_ts,
        )


@dataclass(slots=True)
class KrakenUniverseSupervisor:
    """Keep the fixed Kraken universe aligned with the active worker set."""

    timeframe: str
    worker_factory: Callable[[str, str], KrakenCandleWorker]

    def build_workers(self) -> list[KrakenCandleWorker]:
        """Create one worker per fixed-universe pair."""

        return [self.worker_factory(symbol, self.timeframe) for symbol in KRAKEN_UNIVERSE]
