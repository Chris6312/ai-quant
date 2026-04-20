"""Candle read endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_candle_repository
from app.db.models import CandleRow
from app.repositories.candles import CandleRepository

router = APIRouter(prefix="/candles", tags=["candles"])


@router.get("")
async def list_candles(
    repository: Annotated[CandleRepository, Depends(get_candle_repository)],
    symbol: str = Query(min_length=1),
    timeframe: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    """Return recent candles for a symbol and timeframe."""

    rows = await repository.list_recent(symbol=symbol, timeframe=timeframe, limit=limit)
    return [_serialize_candle(row) for row in rows]


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
    }
