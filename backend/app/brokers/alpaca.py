from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from itertools import batched

import httpx

from app.config.constants import (
    ALPACA_BATCH_MAX_SYMBOLS,
    ALPACA_DEFAULT_SOURCE,
    ALPACA_SYNC_LOOKBACK_DAYS,
)
from app.db.models import CandleRow
from app.exceptions import ResearchAPIError, ResearchParseError
from app.models.domain import Candle
from app.repositories.candles import CandleRepository

type RawBar = Mapping[str, object]
type RawBatch = dict[str, list[RawBar]]

type HttpScalar = str | int | float | bool | None
type HttpValue = HttpScalar | Sequence[HttpScalar]
type HttpParams = Mapping[str, HttpValue]


def _as_float(value: object | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ResearchParseError("invalid numeric value in Alpaca response")


def _as_str(value: object | None) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_params(params: Mapping[str, object]) -> dict[str, HttpValue]:
    result: dict[str, HttpValue] = {}

    for key, value in params.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            result[key] = [
                str(item)
                if not isinstance(item, (str, int, float, bool, type(None)))
                else item
                for item in value
            ]
        else:
            result[key] = str(value)

    return result


class AlpacaTrainingFetcher:
    max_symbols_per_request: int = ALPACA_BATCH_MAX_SYMBOLS

    def __init__(
        self,
        repository: CandleRepository | None = None,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        lookback_days: int = ALPACA_SYNC_LOOKBACK_DAYS,
    ) -> None:
        self.repository = repository
        self.client = client
        self.lookback_days = lookback_days
        self.headers: dict[str, str] | None = None

        if api_key and api_secret:
            self.headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            }

    async def _get(
        self,
        url: str,
        *,
        params: HttpParams | None = None,
    ) -> Mapping[str, object]:
        client = self.client or httpx.AsyncClient()

        response = await client.get(
            url,
            params=params,
            headers=self.headers,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, Mapping):
            raise ResearchParseError("invalid alpaca response")

        return data

    def _parse_bar(
        self,
        symbol: str,
        timeframe: str,
        raw: RawBar,
    ) -> Candle:
        ts_raw = raw.get("t")
        if not isinstance(ts_raw, str):
            raise ResearchParseError("missing timestamp")

        ts = datetime.fromisoformat(
            ts_raw.replace("Z", "+00:00"),
        ).astimezone(UTC)

        return Candle(
            symbol=symbol,
            asset_class="stock",
            timeframe=timeframe,
            time=ts,
            open=_as_float(raw.get("o")),
            high=_as_float(raw.get("h")),
            low=_as_float(raw.get("l")),
            close=_as_float(raw.get("c")),
            volume=_as_float(raw.get("v")),
            source=ALPACA_DEFAULT_SOURCE,
        )

    def _calculate_start(
        self,
        symbols: Sequence[str],
        latest_times: Mapping[str, datetime | None],
    ) -> datetime:
        starts: list[datetime] = []

        for symbol in symbols:
            latest_time = latest_times.get(symbol)

            if latest_time is None:
                starts.append(datetime.now(UTC) - timedelta(days=self.lookback_days))
            else:
                starts.append(latest_time + timedelta(minutes=1))

        return min(starts)

    def _rows_from_batch(
        self,
        batch: dict[str, list[Candle]],
        timeframe: str,
    ) -> list[CandleRow]:
        rows: list[CandleRow] = []

        for symbol, candles in batch.items():
            for candle in candles:
                rows.append(
                    CandleRow(
                        symbol=symbol,
                        asset_class=candle.asset_class,
                        timeframe=timeframe,
                        time=candle.time,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        source=candle.source,
                    )
                )

        return rows

    async def fetch_batch(
        self,
        symbols: Sequence[str],
        timeframe: str,
        *,
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Candle]]:
        params = _coerce_params(
            {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10_000,
                "adjustment": "raw",
                "feed": "iex",
                "sort": "asc",
            }
        )

        payload = await self._get(
            "https://data.alpaca.markets/v2/stocks/bars",
            params=params,
        )

        bars = payload.get("bars")
        if not isinstance(bars, Mapping):
            raise ResearchParseError("missing bars")

        result: dict[str, list[Candle]] = {}

        for symbol in symbols:
            raw_list = bars.get(symbol, [])
            candles: list[Candle] = []

            for raw in raw_list:
                if isinstance(raw, Mapping):
                    candles.append(self._parse_bar(symbol, timeframe, raw))

            result[symbol] = candles

        return result

    async def sync_universe(
        self,
        symbols: Sequence[str],
        timeframes: Sequence[str],
    ) -> int:
        if self.repository is None:
            raise RuntimeError("repository required")

        total_rows = 0

        for timeframe in timeframes:
            latest_times = await self.repository.get_latest_candle_times(
                symbols,
                timeframe,
                source=ALPACA_DEFAULT_SOURCE,
            )
            start = self._calculate_start(symbols, latest_times)
            end = datetime.now(UTC)

            for batch_symbols in batched(symbols, self.max_symbols_per_request):
                batch_tuple = tuple(batch_symbols)
                if not batch_tuple:
                    continue

                candles_by_symbol = await self.fetch_batch(
                    batch_tuple,
                    timeframe,
                    start=start,
                    end=end,
                )
                rows = self._rows_from_batch(candles_by_symbol, timeframe)

                if not rows:
                    continue

                await self.repository.bulk_upsert(rows)
                total_rows += len(rows)

        return total_rows

    async def get_top_gainers(
        self,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        params = _coerce_params({"top": limit})

        payload = await self._get(
            "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives",
            params=params,
        )

        raw_gainers = payload.get("most_actives")
        if not isinstance(raw_gainers, Sequence):
            raise ResearchAPIError("invalid screener response")

        gainers: list[dict[str, object]] = []

        for item in raw_gainers:
            if not isinstance(item, Mapping):
                continue

            symbol = _as_str(item.get("symbol")).upper()
            if not symbol:
                continue

            gainers.append(
                {
                    "symbol": symbol,
                    "price": item.get("price"),
                    "percent_change": item.get("percent_change"),
                    "volume": item.get("volume"),
                }
            )

        return gainers[:limit]

    async def fetch_most_active(
        self,
        top: int = 20,
    ) -> list[dict[str, object]]:
        """Backward-compatible alias used by ML routes."""

        return await self.get_top_gainers(limit=top)