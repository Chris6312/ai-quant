"""Kraken REST OHLCV client for crypto candle backfills and syncs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx

from app.models.domain import Candle

DEFAULT_KRAKEN_BASE_URL = "https://api.kraken.com/0/public"
KRAKEN_OHLC_PATH = "/OHLC"
KRAKEN_PAIR_MAP: dict[str, str] = {
    "BTC/USD": "XBTUSD",
    "ETH/USD": "ETHUSD",
    "SOL/USD": "SOLUSD",
    "XRP/USD": "XRPUSD",
    "ADA/USD": "ADAUSD",
    "AVAX/USD": "AVAXUSD",
    "DOT/USD": "DOTUSD",
    "LINK/USD": "LINKUSD",
    "MATIC/USD": "POLUSD",
    "LTC/USD": "LTCUSD",
    "UNI/USD": "UNIUSD",
    "ATOM/USD": "ATOMUSD",
    "NEAR/USD": "NEARUSD",
    "ALGO/USD": "ALGOUSD",
    "FIL/USD": "FILUSD",
}
KRAKEN_INTERVALS: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1Day": 1440,
}


class KrakenRestCandleClient:
    """Fetch OHLCV candles from Kraken public REST endpoints."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_KRAKEN_BASE_URL,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout_s = timeout_s

    async def fetch_confirmed_candle(
        self,
        symbol: str,
        timeframe: str,
        candle_close_ts: datetime,
    ) -> Candle:
        """Fetch the latest confirmed Kraken candle for one symbol/timeframe."""

        normalized_symbol = self._normalize_symbol(symbol)
        pair = KRAKEN_PAIR_MAP[normalized_symbol]
        interval = KRAKEN_INTERVALS[timeframe]
        since = int(candle_close_ts.timestamp())

        payload = await self._request_with_client(pair=pair, interval=interval, since=since)
        rows = self._extract_rows(payload, pair)
        candles = self._parse_rows(
            rows=rows,
            symbol=normalized_symbol,
            timeframe=timeframe,
        )
        if not candles:
            raise ValueError(f"No confirmed Kraken candle returned for {normalized_symbol}")
        return candles[-1]

    async def fetch_history(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Candle]:
        """Fetch historical Kraken candles for one symbol/timeframe window."""

        normalized_symbol = self._normalize_symbol(symbol)
        pair = KRAKEN_PAIR_MAP[normalized_symbol]
        interval = KRAKEN_INTERVALS[timeframe]
        since = int(start.timestamp())

        payload = await self._request_with_client(pair=pair, interval=interval, since=since)
        rows = self._extract_rows(payload, pair)
        start_utc = start.astimezone(UTC)
        end_utc = end.astimezone(UTC)
        return [
            candle
            for candle in self._parse_rows(
                rows=rows,
                symbol=normalized_symbol,
                timeframe=timeframe,
            )
            if start_utc <= candle.time <= end_utc
        ]

    async def _request_with_client(
        self,
        *,
        pair: str,
        interval: int,
        since: int,
    ) -> Mapping[str, Any]:
        if self._client is not None:
            return await self._request(
                self._client,
                pair=pair,
                interval=interval,
                since=since,
            )
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            return await self._request(client, pair=pair, interval=interval, since=since)

    async def _request(
        self,
        client: httpx.AsyncClient,
        *,
        pair: str,
        interval: int,
        since: int,
    ) -> Mapping[str, Any]:
        response = await client.get(
            f"{self._base_url}{KRAKEN_OHLC_PATH}",
            params={"pair": pair, "interval": interval, "since": since},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("Kraken OHLC response must be an object")
        errors = payload.get("error", [])
        if isinstance(errors, list) and errors:
            raise ValueError(f"Kraken OHLC error for {pair}: {errors}")
        return cast(Mapping[str, Any], payload)

    def _extract_rows(self, payload: Mapping[str, Any], pair: str) -> Sequence[Sequence[Any]]:
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ValueError(f"Kraken OHLC result missing for {pair}")
        raw_rows = result.get(pair)
        if raw_rows is None:
            raw_rows = next(
                (value for key, value in result.items() if key != "last"),
                None,
            )
        if not isinstance(raw_rows, list):
            raise ValueError(f"Kraken OHLC rows missing for {pair}")
        return cast(Sequence[Sequence[Any]], raw_rows)

    def _parse_rows(
        self,
        *,
        rows: Sequence[Sequence[Any]],
        symbol: str,
        timeframe: str,
    ) -> list[Candle]:
        candles: list[Candle] = []
        for row in rows:
            if len(row) < 7:
                continue
            volume = float(row[6])
            if volume <= 0:
                continue
            candles.append(
                Candle(
                    time=datetime.fromtimestamp(float(row[0]), tz=UTC),
                    symbol=symbol,
                    asset_class="crypto",
                    timeframe=timeframe,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=volume,
                    source="kraken",
                )
            )
        return candles

    def _normalize_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.upper().replace("XBT/USD", "BTC/USD")
        if normalized_symbol not in KRAKEN_PAIR_MAP:
            raise ValueError(f"Unsupported Kraken symbol: {symbol}")
        return normalized_symbol


def candle_window(candle_close_ts: datetime, timeframe: str) -> tuple[datetime, datetime]:
    """Return the approximate start/end window for a candle close timestamp."""

    interval_minutes = KRAKEN_INTERVALS[timeframe]
    end = candle_close_ts.astimezone(UTC)
    start = end - timedelta(minutes=interval_minutes)
    return start, end


# Backward-compatible name used by Phase 5 tests and older wiring.
KrakenRestCandleSourceClient = KrakenRestCandleClient
