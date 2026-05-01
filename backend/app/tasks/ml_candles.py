"""Celery tasks for ML-lane candle synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import (
    ALPACA_DEFAULT_SOURCE,
    ALPACA_DEFAULT_TIMEFRAME,
    ALPACA_SYNC_LOOKBACK_DAYS,
    ML_CANDLE_USAGE,
)
from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.db.session import build_engine, build_session_factory
from app.repositories.candles import CandleRepository
from app.runtime_events import record_runtime_task_event
from app.tasks.worker import celery_app

CRYPTO_ML_TIMEFRAMES: tuple[str, ...] = (ALPACA_DEFAULT_TIMEFRAME,)
CRYPTO_ML_LOOKBACK_DAYS = ALPACA_SYNC_LOOKBACK_DAYS
_CRYPTO_ALPACA_REQUEST_ALIASES: dict[str, str] = {
    "XDG/USD": "DOGE/USD",
}
_CRYPTO_STORAGE_ALIASES: dict[str, str] = {
    "DOGE/USD": "XDG/USD",
}


@dataclass(frozen=True, slots=True)
class MlCeleryTaskPayload:
    """Typed Celery task submission payload for ML jobs."""

    name: str
    kwargs: dict[str, object]


@celery_app.task(name="tasks.ml_candles.daily_sync")
def ml_daily_sync_task(
    symbols: list[str] | None = None,
    lookback_days: int = CRYPTO_ML_LOOKBACK_DAYS,
) -> dict[str, object]:
    """Sync crypto daily candles into the isolated ML candle lane."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = list(CRYPTO_ML_TIMEFRAMES)
    record_runtime_task_event(
        worker_id="ml:crypto:1D",
        status="starting",
        detail="ML daily candle sync started",
    )
    try:
        row_count = asyncio.run(
            _run_ml_sync(
                symbols=requested_symbols,
                timeframes=requested_timeframes,
                lookback_days=lookback_days,
            )
        )
    except Exception as exc:
        record_runtime_task_event(
            worker_id="ml:crypto:1D",
            status="error",
            detail=f"ML daily candle sync failed: {type(exc).__name__}: {exc}",
        )
        raise

    finished_at = datetime.now(tz=UTC).isoformat()
    record_runtime_task_event(
        worker_id="ml:crypto:1D",
        status="running",
        detail=(
            "ML daily candle sync succeeded: "
            f"{row_count} rows, {len(requested_symbols)} symbols"
        ),
    )
    return {
        "status": "ok",
        "task": "ml_daily_sync",
        "asset_class": "crypto",
        "source": ALPACA_DEFAULT_SOURCE,
        "usage": ML_CANDLE_USAGE,
        "symbol_count": len(requested_symbols),
        "symbols": requested_symbols,
        "timeframes": requested_timeframes,
        "rows": row_count,
        "finished_at": finished_at,
    }


async def _list_existing_crypto_ml_symbols(
    session: AsyncSession,
    requested_symbols: Sequence[str],
) -> list[str]:
    requested_storage_symbols = {
        _CRYPTO_STORAGE_ALIASES.get(symbol, symbol) for symbol in requested_symbols
    }
    if not requested_storage_symbols:
        return []

    statement = (
        select(CandleRow.symbol)
        .where(
            CandleRow.asset_class == "crypto",
            CandleRow.timeframe.in_(CRYPTO_ML_TIMEFRAMES),
            CandleRow.usage == ML_CANDLE_USAGE,
            CandleRow.symbol.in_(requested_storage_symbols),
        )
        .distinct()
        .order_by(CandleRow.symbol)
    )
    result = await session.scalars(statement)
    return [str(symbol) for symbol in result.all()]


def _build_crypto_sync_request_symbols(
    storage_symbols: Sequence[str],
) -> tuple[list[str], dict[str, str]]:
    request_symbols: list[str] = []
    storage_symbol_by_request_symbol: dict[str, str] = {}

    for storage_symbol in storage_symbols:
        request_symbol = _CRYPTO_ALPACA_REQUEST_ALIASES.get(
            storage_symbol, storage_symbol
        )
        request_symbols.append(request_symbol)
        storage_symbol_by_request_symbol[request_symbol] = storage_symbol

    return request_symbols, storage_symbol_by_request_symbol


async def _run_ml_sync(
    *,
    symbols: Sequence[str],
    timeframes: Sequence[str],
    lookback_days: int,
) -> int:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        return await _run_ml_sync_with_session_factory(
            session_factory=session_factory,
            symbols=symbols,
            timeframes=timeframes,
            lookback_days=lookback_days,
        )
    finally:
        await engine.dispose()


async def _run_ml_sync_with_session_factory(
    *,
    session_factory: async_sessionmaker[Any],
    symbols: Sequence[str],
    timeframes: Sequence[str],
    lookback_days: int,
) -> int:
    settings = get_settings()
    async with session_factory() as session:
        storage_symbols = await _list_existing_crypto_ml_symbols(session, symbols)
        if not storage_symbols:
            return 0

        request_symbols, storage_symbol_by_request_symbol = _build_crypto_sync_request_symbols(
            storage_symbols
        )
        repository = CandleRepository(session)
        fetcher = AlpacaTrainingFetcher(
            repository=repository,
            api_key=settings.alpaca_api_key,
            api_secret=settings.alpaca_api_secret,
            lookback_days=lookback_days,
            storage_symbol_by_request_symbol=storage_symbol_by_request_symbol,
            latest_source=None,
        )
        return await fetcher.sync_universe(
            symbols=request_symbols,
            timeframes=timeframes,
            asset_class="crypto",
        )


def build_ml_daily_sync_payload(symbols: Sequence[str]) -> MlCeleryTaskPayload:
    """Return the daily ML candle sync task payload."""

    return MlCeleryTaskPayload(
        name="tasks.ml_candles.daily_sync",
        kwargs={
            "symbols": list(symbols),
            "lookback_days": CRYPTO_ML_LOOKBACK_DAYS,
        },
    )
