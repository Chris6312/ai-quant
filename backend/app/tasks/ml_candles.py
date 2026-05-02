"""Celery tasks for ML-lane candle synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import (
    ALPACA_DEFAULT_SOURCE,
    ALPACA_DEFAULT_TIMEFRAME,
    CRYPTO_ML_TIMEFRAMES,
    ML_CANDLE_USAGE,
    ML_CRYPTO_CONTEXT_WORKER_ID,
    ML_CRYPTO_INTRADAY_WORKER_ID,
    ML_STOCK_INTRADAY_WORKER_ID,
    STOCK_ML_TIMEFRAMES,
)
from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.db.session import build_engine, build_session_factory
from app.ml.stock_universe import StockUniverseLoader
from app.ml.timeframe_config import get_ml_lookback_days
from app.repositories.candles import CandleRepository
from app.runtime_events import record_runtime_task_event
from app.tasks.worker import celery_app

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
) -> dict[str, object]:
    """Backward-compatible alias for the primary crypto intraday ML sync."""

    return cast(dict[str, object], ml_crypto_intraday_sync_task(symbols=symbols))


@celery_app.task(name="tasks.ml_candles.crypto_intraday_sync")
def ml_crypto_intraday_sync_task(
    symbols: list[str] | None = None,
) -> dict[str, object]:
    """Sync crypto intraday candles into the isolated ML candle lane."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = list(CRYPTO_ML_TIMEFRAMES)
    record_runtime_task_event(
        worker_id=ML_CRYPTO_INTRADAY_WORKER_ID,
        status="starting",
        detail="ML crypto intraday candle sync started",
    )
    try:
        row_count = asyncio.run(
            _run_ml_sync(
                asset_class="crypto",
                symbols=requested_symbols,
                timeframes=requested_timeframes,
            )
        )
    except Exception as exc:
        record_runtime_task_event(
            worker_id=ML_CRYPTO_INTRADAY_WORKER_ID,
            status="error",
            detail=f"ML crypto intraday candle sync failed: {type(exc).__name__}: {exc}",
        )
        raise

    finished_at = datetime.now(tz=UTC).isoformat()
    record_runtime_task_event(
        worker_id=ML_CRYPTO_INTRADAY_WORKER_ID,
        status="running",
        detail=(
            "ML crypto intraday candle sync succeeded: "
            f"{row_count} rows, {len(requested_symbols)} symbols"
        ),
    )
    return {
        "status": "ok",
        "task": "ml_crypto_intraday_sync",
        "asset_class": "crypto",
        "source": ALPACA_DEFAULT_SOURCE,
        "usage": ML_CANDLE_USAGE,
        "symbol_count": len(requested_symbols),
        "symbols": requested_symbols,
        "timeframes": requested_timeframes,
        "rows": row_count,
        "finished_at": finished_at,
    }


@celery_app.task(name="tasks.ml_candles.crypto_context_sync")
def ml_crypto_context_sync_task(
    symbols: list[str] | None = None,
) -> dict[str, object]:
    """Sync crypto daily candles for context/research only."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = [ALPACA_DEFAULT_TIMEFRAME]
    record_runtime_task_event(
        worker_id=ML_CRYPTO_CONTEXT_WORKER_ID,
        status="starting",
        detail="ML crypto daily context candle sync started",
    )
    try:
        row_count = asyncio.run(
            _run_ml_sync(
                asset_class="crypto",
                symbols=requested_symbols,
                timeframes=requested_timeframes,
            )
        )
    except Exception as exc:
        record_runtime_task_event(
            worker_id=ML_CRYPTO_CONTEXT_WORKER_ID,
            status="error",
            detail=f"ML crypto daily context candle sync failed: {type(exc).__name__}: {exc}",
        )
        raise

    finished_at = datetime.now(tz=UTC).isoformat()
    record_runtime_task_event(
        worker_id=ML_CRYPTO_CONTEXT_WORKER_ID,
        status="running",
        detail=(
            "ML crypto daily context candle sync succeeded: "
            f"{row_count} rows, {len(requested_symbols)} symbols"
        ),
    )
    return {
        "status": "ok",
        "task": "ml_crypto_context_sync",
        "asset_class": "crypto",
        "source": ALPACA_DEFAULT_SOURCE,
        "usage": ML_CANDLE_USAGE,
        "symbol_count": len(requested_symbols),
        "symbols": requested_symbols,
        "timeframes": requested_timeframes,
        "rows": row_count,
        "finished_at": finished_at,
    }


@celery_app.task(name="tasks.ml_candles.stock_intraday_sync")
def ml_stock_intraday_sync_task(
    symbols: list[str] | None = None,
) -> dict[str, object]:
    """Sync stock intraday candles into the isolated ML candle lane."""

    requested_symbols = symbols or _list_stock_ml_symbols()
    requested_timeframes = list(STOCK_ML_TIMEFRAMES)
    record_runtime_task_event(
        worker_id=ML_STOCK_INTRADAY_WORKER_ID,
        status="starting",
        detail="ML stock intraday candle sync started",
    )
    try:
        row_count = asyncio.run(
            _run_ml_sync(
                asset_class="stock",
                symbols=requested_symbols,
                timeframes=requested_timeframes,
            )
        )
    except Exception as exc:
        record_runtime_task_event(
            worker_id=ML_STOCK_INTRADAY_WORKER_ID,
            status="error",
            detail=f"ML stock intraday candle sync failed: {type(exc).__name__}: {exc}",
        )
        raise

    finished_at = datetime.now(tz=UTC).isoformat()
    record_runtime_task_event(
        worker_id=ML_STOCK_INTRADAY_WORKER_ID,
        status="running",
        detail=(
            "ML stock intraday candle sync succeeded: "
            f"{row_count} rows, {len(requested_symbols)} symbols"
        ),
    )
    return {
        "status": "ok",
        "task": "ml_stock_intraday_sync",
        "asset_class": "stock",
        "source": ALPACA_DEFAULT_SOURCE,
        "usage": ML_CANDLE_USAGE,
        "symbol_count": len(requested_symbols),
        "symbols": requested_symbols,
        "timeframes": requested_timeframes,
        "rows": row_count,
        "finished_at": finished_at,
    }


def _list_stock_ml_symbols() -> list[str]:
    snapshot = StockUniverseLoader().load()
    return [symbol.provider_symbol for symbol in snapshot.supported_symbols]


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


async def _select_crypto_storage_symbols(
    session: AsyncSession,
    requested_symbols: Sequence[str],
) -> list[str]:
    storage_symbols = [
        _CRYPTO_STORAGE_ALIASES.get(symbol, symbol) for symbol in requested_symbols
    ]
    existing_symbols = await _list_existing_crypto_ml_symbols(session, requested_symbols)
    if existing_symbols:
        known = set(existing_symbols)
        return [symbol for symbol in storage_symbols if symbol in known]
    return storage_symbols


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
    asset_class: str,
    symbols: Sequence[str],
    timeframes: Sequence[str],
) -> int:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        return await _run_ml_sync_with_session_factory(
            session_factory=session_factory,
            asset_class=asset_class,
            symbols=symbols,
            timeframes=timeframes,
        )
    finally:
        await engine.dispose()


async def _run_ml_sync_with_session_factory(
    *,
    session_factory: async_sessionmaker[Any],
    asset_class: str,
    symbols: Sequence[str],
    timeframes: Sequence[str],
) -> int:
    settings = get_settings()
    async with session_factory() as session:
        if asset_class == "crypto":
            storage_symbols = await _select_crypto_storage_symbols(session, symbols)
            request_symbols, storage_symbol_by_request_symbol = _build_crypto_sync_request_symbols(
                storage_symbols
            )
            latest_source = None
        else:
            request_symbols = list(symbols)
            storage_symbol_by_request_symbol = {}
            latest_source = ALPACA_DEFAULT_SOURCE

        if not request_symbols:
            return 0

        repository = CandleRepository(session)
        total_rows = 0
        for timeframe in timeframes:
            fetcher = AlpacaTrainingFetcher(
                repository=repository,
                api_key=settings.alpaca_api_key,
                api_secret=settings.alpaca_api_secret,
                lookback_days=get_ml_lookback_days(asset_class, timeframe),
                storage_symbol_by_request_symbol=storage_symbol_by_request_symbol,
                latest_source=latest_source,
            )
            total_rows += await fetcher.sync_universe(
                symbols=request_symbols,
                timeframes=[timeframe],
                asset_class=asset_class,
            )
        return total_rows


def build_ml_daily_sync_payload(symbols: Sequence[str]) -> MlCeleryTaskPayload:
    """Return the primary ML candle sync task payload."""

    return MlCeleryTaskPayload(
        name="tasks.ml_candles.crypto_intraday_sync",
        kwargs={
            "symbols": list(symbols),
        },
    )
