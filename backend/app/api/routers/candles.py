"""Candle read endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_candle_repository
from app.config.constants import TRADING_CANDLE_USAGE
from app.db.models import CandleRow
from app.repositories.candles import CandleRepository

router = APIRouter(prefix="/candles", tags=["candles"])

KRAKEN_PUBLIC_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
KRAKEN_TICKER_SYMBOLS: tuple[str, ...] = (
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
KRAKEN_TICKER_PAIR_MAP: dict[str, str] = {
    "BTC/USD": "XBTUSD",
    "ETH/USD": "ETHUSD",
    "SOL/USD": "SOLUSD",
    "LTC/USD": "LTCUSD",
    "BCH/USD": "BCHUSD",
    "LINK/USD": "LINKUSD",
    "UNI/USD": "UNIUSD",
    "AVAX/USD": "AVAXUSD",
    "DOGE/USD": "DOGEUSD",
    "DOT/USD": "DOTUSD",
    "AAVE/USD": "AAVEUSD",
    "CRV/USD": "CRVUSD",
    "SUSHI/USD": "SUSHIUSD",
    "SHIB/USD": "SHIBUSD",
    "XTZ/USD": "XTZUSD",
}


@router.get("")
async def list_candles(
    symbol: Annotated[str, Query(min_length=1)],
    timeframe: Annotated[str, Query(min_length=1)],
    repository: Annotated[CandleRepository, Depends(get_candle_repository)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    usage: Annotated[str, Query(pattern="^(trading|ml)$")] = TRADING_CANDLE_USAGE,
) -> list[dict[str, object]]:
    """Return recent candles for a symbol, timeframe, and candle lane."""

    rows = await repository.list_recent(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        usage=usage,
    )
    return [_serialize_candle(row) for row in rows]


@router.get("/kraken-ticker")
async def get_kraken_ticker(
    symbols: Annotated[str | None, Query()] = None,
) -> list[dict[str, object]]:
    """Return a lightweight Kraken ticker snapshot for dashboard display."""

    requested_symbols = _parse_requested_symbols(symbols)
    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await _fetch_kraken_tickers(client, requested_symbols)
    return results


def _parse_requested_symbols(symbols: str | None) -> list[str]:
    """Parse and validate an optional comma-separated symbol list."""

    if symbols is None or not symbols.strip():
        return list(KRAKEN_TICKER_SYMBOLS)

    requested_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    normalized_symbols: list[str] = []
    for raw_symbol in requested_symbols:
        normalized_symbol = raw_symbol.replace("XBT/USD", "BTC/USD")
        if normalized_symbol not in KRAKEN_TICKER_PAIR_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported Kraken ticker symbol: {raw_symbol}",
            )
        normalized_symbols.append(normalized_symbol)
    return normalized_symbols


async def _fetch_kraken_tickers(
    client: httpx.AsyncClient,
    symbols: Sequence[str],
) -> list[dict[str, object]]:
    """Fetch ticker snapshots concurrently from Kraken."""

    tasks = [_fetch_single_kraken_ticker(client, symbol) for symbol in symbols]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    tickers: list[dict[str, object]] = []
    errors: list[str] = []
    for response in responses:
        if isinstance(response, BaseException):
            errors.append(str(response))
            continue
        tickers.append(response)

    if not tickers:
        detail = errors[0] if errors else "Kraken ticker request failed."
        raise HTTPException(status_code=502, detail=detail)

    return tickers


async def _fetch_single_kraken_ticker(
    client: httpx.AsyncClient,
    symbol: str,
) -> dict[str, object]:
    """Fetch and normalize a single Kraken ticker snapshot."""

    pair = KRAKEN_TICKER_PAIR_MAP[symbol]
    response = await client.get(KRAKEN_PUBLIC_TICKER_URL, params={"pair": pair})
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail=f"Kraken ticker payload malformed for {symbol}.",
        )

    error_messages = payload.get("error", [])
    if error_messages:
        raise HTTPException(
            status_code=502,
            detail=f"Kraken ticker error for {symbol}: {error_messages}",
        )

    result = payload.get("result")
    if not isinstance(result, dict) or len(result) == 0:
        raise HTTPException(
            status_code=502,
            detail=f"Kraken ticker payload missing result for {symbol}.",
        )

    ticker_payload = next(iter(result.values()))
    if not isinstance(ticker_payload, dict):
        raise HTTPException(
            status_code=502,
            detail=f"Kraken ticker payload malformed for {symbol}.",
        )

    close_values = ticker_payload.get("c")
    open_value = ticker_payload.get("o")
    if not isinstance(close_values, list) or len(close_values) == 0 or open_value is None:
        raise HTTPException(
            status_code=502,
            detail=f"Kraken ticker payload missing fields for {symbol}.",
        )

    last_price = float(close_values[0])
    open_price = float(open_value)
    change_pct = 0.0 if open_price == 0 else ((last_price - open_price) / open_price) * 100.0

    return {
        "symbol": symbol,
        "last_price": last_price,
        "open_price": open_price,
        "change_pct": change_pct,
        "source": "kraken_ticker",
    }


def _serialize_candle(row: CandleRow) -> dict[str, object]:
    """Convert a candle row to an API payload."""

    return {
        "time": row.time.isoformat(),
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "timeframe": row.timeframe,
        "open": float(row.open) if row.open is not None else None,
        "high": float(row.high) if row.high is not None else None,
        "low": float(row.low) if row.low is not None else None,
        "close": float(row.close) if row.close is not None else None,
        "volume": float(row.volume) if row.volume is not None else None,
        "source": row.source,
        "usage": row.usage,
    }