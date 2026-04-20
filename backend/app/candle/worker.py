"""Base candle worker with Redis locking and persistence."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol

from app.config.constants import (
    CANDLE_FETCH_DELAY_SECONDS,
    CANDLE_HEARTBEAT_TTL_SECONDS,
    CANDLE_LOCK_TTL_SECONDS,
)
from app.db.models import CandleRow
from app.exceptions import CandleValidationError
from app.models.domain import Candle
from app.repositories.candles import CandleRepository


class RedisClient(Protocol):
    """Define the Redis operations needed by candle workers."""

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
    ) -> bool | None:
        """Set a Redis key."""

    async def expire(self, name: str, time: int) -> bool:
        """Set a Redis key expiry."""

    async def publish(self, channel: str, message: str) -> int:
        """Publish a Redis message."""


class CandleSourceClient(Protocol):
    """Define the live candle data contract for workers."""

    async def stream_candle_closes(self, symbol: str, timeframe: str) -> AsyncIterator[datetime]:
        """Yield candle-close timestamps for a symbol/timeframe pair."""

    async def fetch_confirmed_candle(
        self,
        symbol: str,
        timeframe: str,
        close_time: datetime,
    ) -> Candle:
        """Fetch a confirmed candle after the close delay."""


class CandleWorker(ABC):
    """Shared worker behavior for live market-data consumers."""

    def __init__(
        self,
        symbol: str,
        asset_class: str,
        timeframe: str,
        source: str,
        repository: CandleRepository,
        redis_client: RedisClient,
        client: CandleSourceClient,
        delay_s: int = CANDLE_FETCH_DELAY_SECONDS,
        lock_ttl_s: int = CANDLE_LOCK_TTL_SECONDS,
        heartbeat_ttl_s: int = CANDLE_HEARTBEAT_TTL_SECONDS,
    ) -> None:
        self.symbol = symbol
        self.asset_class = asset_class
        self.timeframe = timeframe
        self.source = source
        self.repository = repository
        self.redis = redis_client
        self.client = client
        self.delay_s = delay_s
        self.lock_ttl_s = lock_ttl_s
        self.heartbeat_ttl_s = heartbeat_ttl_s

    @property
    def lock_key(self) -> str:
        """Return the distributed lock key."""

        return f"candle_worker:{self.asset_class}:{self.symbol}:{self.timeframe}"

    @property
    def heartbeat_key(self) -> str:
        """Return the heartbeat key."""

        return f"candle_heartbeat:{self.asset_class}:{self.symbol}:{self.timeframe}"

    @property
    def channel_name(self) -> str:
        """Return the Redis publish channel for candle-close events."""

        return f"candle_closed:{self.asset_class}:{self.symbol}:{self.timeframe}"

    async def run(self) -> None:
        """Run the worker until the source stream ends or the task is cancelled."""

        acquired = await self.redis.set(self.lock_key, "1", nx=True, ex=self.lock_ttl_s)
        if not acquired:
            raise RuntimeError(
                f"Worker already running: {self.asset_class}/{self.symbol}/{self.timeframe}"
            )

        async for candle_close_ts in self._stream_candle_closes():
            await self.process_candle_close(candle_close_ts)

    async def process_candle_close(self, candle_close_ts: datetime) -> Candle:
        """Fetch, validate, persist, and publish one candle close event."""

        await asyncio.sleep(self.delay_s)
        await self.redis.expire(self.lock_key, self.lock_ttl_s)
        await self.redis.set(
            self.heartbeat_key,
            datetime.now(tz=UTC).isoformat(),
            ex=self.heartbeat_ttl_s,
        )
        candle = await self._fetch_confirmed_candle(candle_close_ts)
        self.validate_candle(candle)
        await self._persist(candle)
        await self.redis.publish(self.channel_name, self._serialize_candle(candle))
        return candle

    def validate_candle(self, candle: Candle) -> None:
        """Validate the candle shape before persistence."""

        if candle.symbol != self.symbol:
            raise CandleValidationError("Candle symbol mismatch")
        if candle.asset_class != self.asset_class:
            raise CandleValidationError("Candle asset class mismatch")
        if candle.timeframe != self.timeframe:
            raise CandleValidationError("Candle timeframe mismatch")
        if candle.time.tzinfo is None:
            raise CandleValidationError("Candle time must be timezone-aware")
        if candle.volume <= 0.0:
            raise CandleValidationError("Candle volume must be positive")
        if candle.high < candle.low:
            raise CandleValidationError("Candle high must be >= low")
        if candle.open <= 0.0 or candle.close <= 0.0:
            raise CandleValidationError("Candle prices must be positive")

    async def _persist(self, candle: Candle) -> None:
        """Persist a validated candle to TimescaleDB."""

        row = CandleRow(
            time=candle.time,
            symbol=candle.symbol,
            asset_class=candle.asset_class,
            timeframe=candle.timeframe,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            source=candle.source,
        )
        await self.repository.bulk_upsert([row])

    def _serialize_candle(self, candle: Candle) -> str:
        """Serialize a candle for Redis pub/sub."""

        payload = asdict(candle)
        payload["time"] = candle.time.isoformat()
        return json.dumps(payload, separators=(",", ":"))

    @abstractmethod
    async def _stream_candle_closes(self) -> AsyncIterator[datetime]:
        """Stream candle close timestamps from the underlying market feed."""

    @abstractmethod
    async def _fetch_confirmed_candle(self, candle_close_ts: datetime) -> Candle:
        """Fetch a confirmed candle after the close delay."""
