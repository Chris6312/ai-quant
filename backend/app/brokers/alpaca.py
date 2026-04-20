"""Alpaca batch OHLCV fetcher for ML training only.

This module is intentionally isolated from live-trading code paths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import batched

import httpx

from app.config.constants import (
    ALPACA_BATCH_MAX_SYMBOLS,
    ALPACA_DEFAULT_SOURCE,
    ALPACA_SYNC_LOOKBACK_DAYS,
)
from app.db.models import CandleRow
from app.exceptions import ResearchAPIError, ResearchParseError, TrainingDataValidationError
from app.models.domain import Candle
from app.repositories.candles import CandleRepository

CandleBatch = dict[str, list[Candle]]
type RawAlpacaBar = Mapping[str, object]
type RawAlpacaBatch = dict[str, list[RawAlpacaBar]]


@dataclass(slots=True, frozen=True)
class AlpacaBar:
    """Represent one Alpaca bar payload."""

    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class AlpacaTrainingFetcher:
    """Fetch historical OHLCV bars for training data only."""

    def __init__(
        self,
        repository: CandleRepository | None = None,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://data.alpaca.markets/v2",
        api_key: str | None = None,
        api_secret: str | None = None,
        source: str = ALPACA_DEFAULT_SOURCE,
        max_symbols_per_request: int = ALPACA_BATCH_MAX_SYMBOLS,
        lookback_days: int = ALPACA_SYNC_LOOKBACK_DAYS,
    ) -> None:
        self.repository = repository
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.source = source
        self.max_symbols_per_request = max_symbols_per_request
        self.lookback_days = lookback_days

    async def fetch_batch(
        self,
        symbols: Sequence[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> CandleBatch:
        """Fetch OHLCV for a batch of symbols."""

        self._validate_symbol_batch(symbols)
        headers = self._auth_headers()
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(),
            "adjustment": "all",
            "feed": "sip",
            "limit": 10_000,
        }
        try:
            response = await self._get(
                f"{self.base_url}/stocks/bars",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchAPIError("Unable to fetch Alpaca batch bars") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchParseError("Alpaca payload is not valid JSON") from exc
        bars = self._extract_bars(payload)
        parsed = {
            symbol: [self._parse_candle(symbol, bar, timeframe) for bar in items]
            for symbol, items in bars.items()
        }
        self._validate_batches(parsed, timeframe)
        return parsed

    async def sync_universe(
        self,
        symbols: Sequence[str],
        timeframes: Sequence[str],
    ) -> int:
        """Fetch and persist the incremental delta for a symbol universe."""

        if self.repository is None:
            raise TrainingDataValidationError("Alpaca sync requires a candle repository")
        total_rows = 0
        end = datetime.now(tz=UTC)
        for timeframe in timeframes:
            for symbol_batch in batched(symbols, self.max_symbols_per_request):
                batch_symbols = list(symbol_batch)
                latest_times = await self.repository.get_latest_candle_times(
                    batch_symbols,
                    timeframe,
                    source=self.source,
                )
                start = self._calculate_start(batch_symbols, latest_times)
                batch = await self.fetch_batch(batch_symbols, timeframe, start=start, end=end)
                rows = self._rows_from_batch(batch, timeframe, latest_times)
                if rows:
                    await self.repository.bulk_upsert(rows)
                    total_rows += len(rows)
        return total_rows

    def _auth_headers(self) -> dict[str, str]:
        """Return Alpaca auth headers when credentials are configured."""

        headers: dict[str, str] = {}
        if self.api_key is not None:
            headers["APCA-API-KEY-ID"] = self.api_key
        if self.api_secret is not None:
            headers["APCA-API-SECRET-KEY"] = self.api_secret
        return headers

    async def _get(
        self,
        url: str,
        params: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        """Perform an HTTP GET with either an injected or temporary client."""

        if self.client is not None:
            return await self.client.get(url, params=params, headers=headers)
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, params=params, headers=headers)

    def _validate_symbol_batch(self, symbols: Sequence[str]) -> None:
        """Ensure a batch does not exceed the configured Alpaca limit."""

        if not symbols:
            raise TrainingDataValidationError("Symbol batch cannot be empty")
        if len(symbols) > self.max_symbols_per_request:
            raise TrainingDataValidationError("Symbol batch exceeds Alpaca limit")

    def _extract_bars(self, payload: object) -> RawAlpacaBatch:
        """Extract bar lists from a response payload."""

        if not isinstance(payload, Mapping):
            raise ResearchParseError("Alpaca payload must be a mapping")
        raw_bars = payload.get("bars", payload)
        if not isinstance(raw_bars, Mapping):
            raise ResearchParseError("Alpaca bars payload must be a mapping")
        extracted: RawAlpacaBatch = {}
        for symbol, series in raw_bars.items():
            if not isinstance(symbol, str):
                raise ResearchParseError("Alpaca symbol key must be a string")
            inner = series["bars"] if isinstance(series, Mapping) and "bars" in series else series
            if not isinstance(inner, Sequence) or isinstance(inner, (str, bytes, bytearray)):
                raise ResearchParseError("Alpaca symbol bars must be a sequence")
            extracted[symbol] = [item for item in inner if isinstance(item, Mapping)]
        return extracted

    def _parse_candle(self, symbol: str, bar: Mapping[str, object], timeframe: str) -> Candle:
        """Parse one Alpaca bar into a domain candle."""

        time_value = bar.get("t") or bar.get("time") or bar.get("timestamp")
        if not isinstance(time_value, str):
            raise TrainingDataValidationError("Alpaca bar missing time")
        time = self._parse_datetime(time_value)
        open_price = self._parse_float(bar.get("o") or bar.get("open"))
        high_price = self._parse_float(bar.get("h") or bar.get("high"))
        low_price = self._parse_float(bar.get("l") or bar.get("low"))
        close_price = self._parse_float(bar.get("c") or bar.get("close"))
        volume = self._parse_float(bar.get("v") or bar.get("volume"))
        return Candle(
            time=time,
            symbol=symbol,
            asset_class="stock",
            timeframe=timeframe,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            source=self.source,
        )

    def _parse_datetime(self, value: str) -> datetime:
        """Parse an ISO datetime string."""

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _parse_float(self, value: object) -> float:
        """Parse a numeric payload value."""

        if value is None:
            raise TrainingDataValidationError("Alpaca bar missing numeric value")
        return float(value)

    def _validate_batches(self, batches: CandleBatch, timeframe: str) -> None:
        """Validate candles for each symbol in a batch."""

        expected_delta = self._timeframe_delta(timeframe)
        for symbol, candles in batches.items():
            if not candles:
                continue
            self._validate_series(symbol, candles, expected_delta)

    def _validate_series(
        self,
        symbol: str,
        candles: Sequence[Candle],
        expected_delta: timedelta,
    ) -> None:
        """Validate a single symbol candle series."""

        previous_time: datetime | None = None
        for candle in sorted(candles, key=lambda item: item.time):
            if candle.open <= 0.0 or candle.high < candle.low or candle.close <= 0.0:
                raise TrainingDataValidationError(f"Invalid OHLC values for {symbol}")
            if candle.volume <= 0.0:
                raise TrainingDataValidationError(f"Zero-volume candle for {symbol}")
            if previous_time is not None:
                gap = candle.time - previous_time
                if gap > expected_delta * 3:
                    raise TrainingDataValidationError(f"Gap too large for {symbol}")
            previous_time = candle.time

    def _timeframe_delta(self, timeframe: str) -> timedelta:
        """Map a timeframe label to a timedelta."""

        match timeframe:
            case "1Min":
                return timedelta(minutes=1)
            case "5Min":
                return timedelta(minutes=5)
            case "15Min":
                return timedelta(minutes=15)
            case "1Hour":
                return timedelta(hours=1)
            case "1Day":
                return timedelta(days=1)
            case _:
                raise TrainingDataValidationError(f"Unsupported Alpaca timeframe: {timeframe}")

    def _rows_from_batch(
        self,
        batches: CandleBatch,
        timeframe: str,
        latest_times: Mapping[str, datetime | None],
    ) -> list[CandleRow]:
        """Convert a parsed batch into ORM rows and filter already stored bars."""

        rows: list[CandleRow] = []
        for symbol, candles in batches.items():
            latest = latest_times.get(symbol)
            for candle in candles:
                if latest is not None and candle.time <= latest:
                    continue
                rows.append(
                    CandleRow(
                        time=candle.time,
                        symbol=candle.symbol,
                        asset_class=candle.asset_class,
                        timeframe=timeframe,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        source=candle.source,
                    )
                )
        return rows

    def _calculate_start(
        self,
        symbols: Sequence[str],
        latest_times: Mapping[str, datetime | None],
    ) -> datetime:
        """Compute the earliest start date for a symbol batch."""

        existing_times = [
            time
            for symbol in symbols
            if (time := latest_times.get(symbol)) is not None
        ]
        if not existing_times:
            return datetime.now(tz=UTC) - timedelta(days=self.lookback_days)
        return min(existing_times)
