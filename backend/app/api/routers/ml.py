"""Machine learning and research pipeline triggers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, NamedTuple, Protocol, cast

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_candle_repository
from app.brokers.alpaca import AlpacaTrainingFetcher
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.config.constants import ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.db.session import build_engine, build_session_factory
from app.ml.job_store import create_job, finish_job, update_job
from app.ml.job_store import get_job as load_job
from app.ml.job_store import list_jobs as load_jobs
from app.ml.training_status_cache import (
    get_or_build_training_status,
    mark_training_status_stale,
    rebuild_training_status,
)
from app.repositories.candles import CandleRepository

router = APIRouter(prefix="/ml", tags=["ml"])

_TRAINING_SOURCES = (ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE)


class TrainingStatusRow(NamedTuple):
    symbol: str
    asset_class: str
    timeframe: str
    row_count: int
    earliest: datetime | None
    latest: datetime | None


RawTrainingStatusRow = tuple[object, object, object, object, object, object]


class TrainingStatusResult(Protocol):
    def all(self) -> list[object]:
        """Return grouped training status rows."""


def _resolve_asset_class(job_type: str) -> str:
    if "crypto" in job_type:
        return "crypto"
    if "stock" in job_type:
        return "stock"
    return "mixed"


def _new_job(job_type: str, symbols: list[str]) -> dict[str, object]:
    now = datetime.now(tz=UTC)
    job = create_job(
        {
            "job_id": f"{job_type}-{now.strftime('%Y%m%d-%H%M%S')}",
            "type": job_type,
            "asset_class": _resolve_asset_class(job_type),
            "symbols": symbols,
            "status": "running",
            "started_at": now.isoformat(),
            "finished_at": None,
            "total_symbols": len(symbols),
            "done_symbols": 0,
            "current_symbol": None,
            "current_timeframe": None,
            "total_batches": 0,
            "done_batches": 0,
            "rows_fetched": 0,
            "progress_pct": 0,
            "status_message": "Queued",
            "error": None,
            "result": None,
        }
    )
    return cast(dict[str, object], job)


def _sorted_jobs() -> list[dict[str, object]]:
    return [cast(dict[str, object], job) for job in load_jobs()]


def _active_job() -> dict[str, object] | None:
    return next((job for job in _sorted_jobs() if job.get("status") == "running"), None)


async def _training_status_stmt(session: AsyncSession) -> TrainingStatusResult:
    stmt = (
        select(
            CandleRow.symbol,
            CandleRow.asset_class,
            CandleRow.timeframe,
            func.count().label("row_count"),
            func.min(CandleRow.time).label("earliest"),
            func.max(CandleRow.time).label("latest"),
        )
        .where(CandleRow.source.in_(_TRAINING_SOURCES))
        .group_by(CandleRow.symbol, CandleRow.asset_class, CandleRow.timeframe)
        .order_by(
            CandleRow.asset_class.asc(),
            CandleRow.symbol.asc(),
            CandleRow.timeframe.asc(),
        )
    )
    result = await session.execute(stmt)
    return cast(TrainingStatusResult, result)


async def _load_training_status_rows(session: AsyncSession) -> list[TrainingStatusRow]:
    result = await _training_status_stmt(session)
    rows: list[TrainingStatusRow] = []

    for raw_row in result.all():
        if isinstance(raw_row, TrainingStatusRow):
            rows.append(raw_row)
            continue

        row = cast(RawTrainingStatusRow, raw_row)
        symbol, asset_class, timeframe, row_count, earliest, latest = row
        row_count_value = cast(int | str, row_count)
        rows.append(
            TrainingStatusRow(
                symbol=str(symbol),
                asset_class=str(asset_class),
                timeframe=str(timeframe),
                row_count=int(row_count_value),
                earliest=cast(datetime | None, earliest),
                latest=cast(datetime | None, latest),
            )
        )

    return rows


def _serialize_training_detail(row: TrainingStatusRow) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "timeframe": row.timeframe,
        "candle_count": row.row_count,
        "earliest": row.earliest.isoformat() if row.earliest else None,
        "latest": row.latest.isoformat() if row.latest else None,
    }


async def _build_training_status() -> dict[str, object]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        rows = await _load_training_status_rows(session)

    crypto_detail: list[dict[str, object]] = []
    stock_detail: list[dict[str, object]] = []
    crypto_symbols: set[str] = set()
    stock_symbols: set[str] = set()
    crypto_candles = 0
    stock_candles = 0

    for row in rows:
        detail = _serialize_training_detail(row)

        if row.asset_class == "crypto":
            crypto_detail.append(detail)
            crypto_candles += row.row_count
            if row.row_count > 0:
                crypto_symbols.add(row.symbol)
        else:
            stock_detail.append(detail)
            stock_candles += row.row_count
            if row.row_count > 0:
                stock_symbols.add(row.symbol)

    return {
        "source": ",".join(_TRAINING_SOURCES),
        "total_candles": crypto_candles + stock_candles,
        "crypto_candles": crypto_candles,
        "stock_candles": stock_candles,
        "crypto_symbols": len(crypto_symbols),
        "stock_symbols": len(stock_symbols),
        "symbols_with_data": len(crypto_symbols | stock_symbols),
        "crypto_detail": crypto_detail,
        "stock_detail": stock_detail,
    }


@router.get("/training/status")
async def training_status() -> dict[str, object]:
    status = await get_or_build_training_status(
        _build_training_status,
        allow_stale=_active_job() is not None,
    )
    return cast(dict[str, object], status)


@router.get("/jobs")
async def list_jobs() -> list[dict[str, object]]:
    return _sorted_jobs()


@router.get("/jobs/active")
async def active_job() -> dict[str, object]:
    return {"job": _active_job()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return cast(dict[str, object], job)


class StockBackfillRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1Day"
    lookback_days: int = 365


async def _run_stock_backfill(
    job_id: str,
    symbols: list[str],
    timeframe: str,
    lookback_days: int,
    candle_repo: CandleRepository,
) -> None:
    settings = get_settings()
    mark_training_status_stale("stock_backfill_started")

    fetcher = AlpacaTrainingFetcher(
        repository=candle_repo,
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
        lookback_days=lookback_days,
    )

    total = max(len(symbols), 1)
    rows_written = 0

    try:
        for i, symbol in enumerate(symbols, start=1):
            update_job(
                job_id,
                current_symbol=symbol,
                current_timeframe=timeframe,
                done_symbols=i - 1,
                total_batches=total,
                done_batches=i - 1,
                rows_fetched=rows_written,
                progress_pct=int(((i - 1) / total) * 100),
                status_message=f"fetching {symbol}",
            )

            written = await fetcher.sync_universe(
                symbols=[symbol],
                timeframes=[timeframe],
            )
            rows_written += int(written)

            update_job(
                job_id,
                done_symbols=i,
                total_batches=total,
                done_batches=i,
                rows_fetched=rows_written,
                progress_pct=int((i / total) * 100),
                status_message=f"completed {symbol}",
            )

        await rebuild_training_status(_build_training_status)
        finish_job(
            job_id,
            status="done",
            result={"rows_written": rows_written},
        )
        update_job(job_id, progress_pct=100, status_message="completed")
    except Exception as exc:
        finish_job(job_id, status="error", error=str(exc))
        update_job(job_id, status_message="failed")


@router.post("/backfill/stocks")
async def backfill_stocks(
    payload: StockBackfillRequest,
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
) -> dict[str, object]:
    symbols = [s.strip().upper() for s in payload.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="no symbols provided")

    job = _new_job("stock_backfill", symbols)

    background_tasks.add_task(
        _run_stock_backfill,
        str(job["job_id"]),
        symbols,
        payload.timeframe,
        payload.lookback_days,
        candle_repo,
    )

    return job


@router.get("/gainers")
async def get_top_gainers(
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, object]:
    settings = get_settings()

    if not settings.alpaca_api_key:
        return {"error": "alpaca key missing", "gainers": []}

    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret or "",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives",
            params={"top": limit, "by": "volume"},
            headers=headers,
        )
        response.raise_for_status()
        data = cast(dict[str, object], response.json())

    gainers = cast(list[dict[str, object]], data.get("most-actives", []))

    return {
        "count": len(gainers),
        "gainers": gainers,
        "fetched_at": datetime.now(tz=UTC).isoformat(),
    }


@router.get("/crypto/universe")
async def crypto_universe() -> dict[str, object]:
    return {
        "symbols": sorted(KRAKEN_UNIVERSE),
        "count": len(KRAKEN_UNIVERSE),
    }