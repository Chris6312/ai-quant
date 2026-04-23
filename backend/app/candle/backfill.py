"""Back-fill market candles into TimescaleDB."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.config.constants import ML_CANDLE_USAGE, TRADING_CANDLE_USAGE
from app.db.models import CandleRow
from app.exceptions import CandleValidationError
from app.models.domain import Candle
from app.repositories.candles import CandleRepository


class HistoricalCandleClient(Protocol):
    """Define the historical OHLCV contract for back-fill sources."""

    async def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        """Fetch historical candles for a symbol and timeframe."""


class BackfillService:
    """Seed indicator windows with historical market data."""

    def __init__(
        self,
        repository: CandleRepository,
    ) -> None:
        self.repository = repository

    async def backfill_symbol(
        self,
        symbol: str,
        asset_class: str,
        timeframe: str,
        client: HistoricalCandleClient,
        source: str,
        usage: str,
        lookback_days: int = 30,
    ) -> int:
        """Fetch and persist a historical back-fill window."""

        end = datetime.now(tz=UTC)
        start = end - timedelta(days=lookback_days)
        candles = await client.fetch_history(symbol, timeframe, start, end)
        rows = [self._to_row(candle, asset_class, timeframe, source, usage) for candle in candles]
        self._validate_rows(rows)
        if rows:
            await self.repository.bulk_upsert(rows)
        return len(rows)

    async def backfill_symbols(
        self,
        symbols: Sequence[str],
        asset_class: str,
        timeframes: Sequence[str],
        client: HistoricalCandleClient,
        source: str,
        usage: str,
        lookback_days: int = 30,
    ) -> int:
        """Back-fill multiple symbols across multiple timeframes."""

        total_rows = 0
        for timeframe in timeframes:
            for symbol in symbols:
                total_rows += await self.backfill_symbol(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe=timeframe,
                    client=client,
                    source=source,
                    usage=usage,
                    lookback_days=lookback_days,
                )
        return total_rows

    def _to_row(
        self,
        candle: Candle,
        asset_class: str,
        timeframe: str,
        source: str,
        usage: str,
    ) -> CandleRow:
        """Convert a domain candle to a persistence row."""

        if candle.time.tzinfo is None:
            raise CandleValidationError("Backfill candle time must be timezone-aware")
        if usage not in {ML_CANDLE_USAGE, TRADING_CANDLE_USAGE}:
            raise CandleValidationError("Backfill candle usage must be explicit")
        return CandleRow(
            time=candle.time,
            symbol=candle.symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            source=source,
            usage=usage,
        )

    def _validate_rows(self, rows: Sequence[CandleRow]) -> None:
        """Validate a candle batch before persistence."""

        previous_time: datetime | None = None
        for row in sorted(rows, key=lambda item: item.time):
            if row.open is None or row.high is None or row.low is None or row.close is None:
                raise CandleValidationError("Backfill candle is missing OHLC values")
            if float(row.volume or 0.0) <= 0.0:
                raise CandleValidationError("Backfill candle volume must be positive")
            if float(row.open) <= 0.0 or float(row.close) <= 0.0:
                raise CandleValidationError("Backfill candle prices must be positive")
            if float(row.high) < float(row.low):
                raise CandleValidationError("Backfill candle high must be >= low")
            if previous_time is not None and row.time < previous_time:
                raise CandleValidationError("Backfill candles must be sorted by time")
            previous_time = row.time
