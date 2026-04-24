"""Celery tasks for ML-lane candle synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import (
    ALPACA_DEFAULT_SOURCE,
    ALPACA_DEFAULT_TIMEFRAME,
    ALPACA_SYNC_LOOKBACK_DAYS,
    ML_CANDLE_USAGE,
)
from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.repositories.candles import CandleRepository
from app.tasks.worker import celery_app

CRYPTO_ML_TIMEFRAMES: tuple[str, ...] = (ALPACA_DEFAULT_TIMEFRAME,)
CRYPTO_ML_LOOKBACK_DAYS = ALPACA_SYNC_LOOKBACK_DAYS


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
    row_count = asyncio.run(
        _run_ml_sync(
            symbols=requested_symbols,
            timeframes=requested_timeframes,
            lookback_days=lookback_days,
        )
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
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


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
        repository = CandleRepository(session)
        fetcher = AlpacaTrainingFetcher(
            repository=repository,
            api_key=settings.alpaca_api_key,
            api_secret=settings.alpaca_api_secret,
            lookback_days=lookback_days,
        )
        return await fetcher.sync_universe(
            symbols=symbols,
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
