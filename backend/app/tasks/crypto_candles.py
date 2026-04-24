"""Celery tasks for crypto candle backfill and closed-candle sync."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.candle.backfill import BackfillService
from app.candle.kraken_rest import KrakenRestCandleClient
from app.config.constants import ML_CANDLE_USAGE, TRADING_CANDLE_USAGE
from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.repositories.candles import CandleRepository
from app.tasks.worker import celery_app

CRYPTO_TRADING_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "4h")
CRYPTO_ML_TIMEFRAMES: tuple[str, ...] = ("1d",)
CRYPTO_STRATEGY_BACKFILL_DAYS = 90
CRYPTO_INCREMENTAL_LOOKBACK_DAYS = 3
CRYPTO_ML_BACKFILL_DAYS = 730


@dataclass(frozen=True, slots=True)
class CeleryTaskPayload:
    """Typed Celery task submission payload."""

    name: str
    kwargs: dict[str, object]


@celery_app.task(name="tasks.crypto_candles.initial_backfill")
def crypto_initial_backfill_task(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    lookback_days: int = CRYPTO_STRATEGY_BACKFILL_DAYS,
) -> dict[str, object]:
    """Backfill Kraken trading-lane candles for strategy readiness."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = timeframes or list(CRYPTO_TRADING_TIMEFRAMES)
    row_count = asyncio.run(
        _run_backfill(
            symbols=requested_symbols,
            timeframes=requested_timeframes,
            lookback_days=lookback_days,
            usage=TRADING_CANDLE_USAGE,
        )
    )
    return _task_result(
        task="initial_backfill",
        symbols=requested_symbols,
        timeframes=requested_timeframes,
        rows=row_count,
        usage=TRADING_CANDLE_USAGE,
    )


@celery_app.task(name="tasks.crypto_candles.sync_closed_candles")
def crypto_sync_closed_candles_task(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    lookback_days: int = CRYPTO_INCREMENTAL_LOOKBACK_DAYS,
) -> dict[str, object]:
    """Refresh recent Kraken trading-lane candles after candle close."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = timeframes or list(CRYPTO_TRADING_TIMEFRAMES)
    row_count = asyncio.run(
        _run_backfill(
            symbols=requested_symbols,
            timeframes=requested_timeframes,
            lookback_days=lookback_days,
            usage=TRADING_CANDLE_USAGE,
        )
    )
    return _task_result(
        task="sync_closed_candles",
        symbols=requested_symbols,
        timeframes=requested_timeframes,
        rows=row_count,
        usage=TRADING_CANDLE_USAGE,
    )


@celery_app.task(name="tasks.crypto_candles.ml_daily_backfill")
def crypto_ml_daily_backfill_task(
    symbols: list[str] | None = None,
    lookback_days: int = CRYPTO_ML_BACKFILL_DAYS,
) -> dict[str, object]:
    """Backfill Kraken daily ML-lane candles separately from trading candles."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_timeframes = list(CRYPTO_ML_TIMEFRAMES)
    row_count = asyncio.run(
        _run_backfill(
            symbols=requested_symbols,
            timeframes=requested_timeframes,
            lookback_days=lookback_days,
            usage=ML_CANDLE_USAGE,
        )
    )
    return _task_result(
        task="ml_daily_backfill",
        symbols=requested_symbols,
        timeframes=requested_timeframes,
        rows=row_count,
        usage=ML_CANDLE_USAGE,
    )


async def _run_backfill(
    *,
    symbols: Sequence[str],
    timeframes: Sequence[str],
    lookback_days: int,
    usage: str,
) -> int:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        return await _run_backfill_with_session_factory(
            session_factory=session_factory,
            symbols=symbols,
            timeframes=timeframes,
            lookback_days=lookback_days,
            usage=usage,
        )
    finally:
        await engine.dispose()


async def _run_backfill_with_session_factory(
    *,
    session_factory: async_sessionmaker[Any],
    symbols: Sequence[str],
    timeframes: Sequence[str],
    lookback_days: int,
    usage: str,
) -> int:
    settings = get_settings()
    async with session_factory() as session:
        repository = CandleRepository(session)
        service = BackfillService(repository)
        client = KrakenRestCandleClient(base_url=settings.kraken_base_url)
        return await service.backfill_symbols(
            symbols=symbols,
            asset_class="crypto",
            timeframes=timeframes,
            client=client,
            source="kraken",
            usage=usage,
            lookback_days=lookback_days,
        )


def _task_result(
    *,
    task: str,
    symbols: Sequence[str],
    timeframes: Sequence[str],
    rows: int,
    usage: str,
) -> dict[str, object]:
    return {
        "status": "ok",
        "task": task,
        "asset_class": "crypto",
        "source": "kraken",
        "usage": usage,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "timeframes": list(timeframes),
        "rows": rows,
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


def build_crypto_celery_task_payloads(symbols: Sequence[str]) -> list[CeleryTaskPayload]:
    """Return the Celery work items the runtime scheduler should submit."""

    return [
        CeleryTaskPayload(
            name="tasks.crypto_candles.initial_backfill",
            kwargs={
                "symbols": list(symbols),
                "timeframes": list(CRYPTO_TRADING_TIMEFRAMES),
                "lookback_days": CRYPTO_STRATEGY_BACKFILL_DAYS,
            },
        ),
        CeleryTaskPayload(
            name="tasks.crypto_candles.sync_closed_candles",
            kwargs={
                "symbols": list(symbols),
                "timeframes": list(CRYPTO_TRADING_TIMEFRAMES),
                "lookback_days": CRYPTO_INCREMENTAL_LOOKBACK_DAYS,
            },
        ),
    ]
