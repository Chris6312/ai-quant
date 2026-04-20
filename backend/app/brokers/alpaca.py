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


def _as_str(v: object | None) -> str:
    if v is None:
        return ""
    return str(v)


def _coerce_params(params: Mapping[str, object]) -> dict[str, HttpValue]:
    result: dict[str, HttpValue] = {}

    for k, v in params.items():

        if v is None or isinstance(v, (str, int, float, bool)):
            result[k] = v

        elif isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)):
            result[k] = [
                str(x) if not isinstance(x, (str, int, float, bool, type(None))) else x
                for x in v
            ]

        else:
            result[k] = str(v)

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

        for sym in symbols:

            ts = latest_times.get(sym)

            if ts is None:

                starts.append(
                    datetime.now(UTC) - timedelta(days=self.lookback_days),
                )

            else:

                starts.append(
                    ts + timedelta(minutes=1),
                )

        return min(starts)

    def _rows_from_batch(
        self,
        batch: dict[str, list[Candle]],
        timeframe: str,
    ) -> list[CandleRow]:

        rows: list[CandleRow] = []

        for symbol, candles in batch.items():

            for c in candles:

                rows.append(
                    CandleRow(
                        symbol=symbol,
                        timeframe=timeframe,
                        time=c.time,
                        open=c.open,
                        high=c.high,
                        low=c.low,
                        close=c.close,
                        volume=c.volume,
                        source=c.source,
                    ),
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
            },
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

                    candles.append(
                        self._parse_bar(symbol, timeframe, raw),
                    )

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

            for chunk in batched(
                symbols,
                self.max_symbols_per_request,
            ):

                latest_times = await self.repository.get_latest_candle_times(
                    list(chunk),
                    timeframe,
                    source=ALPACA_DEFAULT_SOURCE,
                )

                start = self._calculate_start(
                    chunk,
                    latest_times,
                )

                batch = await self.fetch_batch(
                    list(chunk),
                    timeframe,
                    start=start,
                    end=datetime.now(UTC),
                )

                rows = self._rows_from_batch(
                    batch,
                    timeframe,
                )

                if rows:

                    await self.repository.bulk_upsert(rows)
                    total_rows += len(rows)

        return total_rows

    async def fetch_most_active(
        self,
        *,
        top: int = 100,
    ) -> list[str]:

        if top < 1 or top > 100:

            raise ResearchAPIError("top must be 1-100")

        params = _coerce_params({"top": top})

        payload = await self._get(
            "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives",
            params=params,
        )

        items = payload.get("most_actives")

        if not isinstance(items, list):

            raise ResearchParseError("missing most_actives")

        symbols: list[str] = []

        for item in items:

            if isinstance(item, Mapping):

                sym = _as_str(
                    item.get("symbol"),
                ).upper().strip()

                if sym:

                    symbols.append(sym)

        return symbols