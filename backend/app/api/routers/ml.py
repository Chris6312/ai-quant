"""Machine learning and research pipeline triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.dependencies import get_candle_repository
from app.brokers.alpaca import AlpacaTrainingFetcher
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.config.constants import ALPACA_DEFAULT_SOURCE
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.repositories.candles import CandleRepository
from app.repositories.watchlist import WatchlistRepository
from app.api.dependencies import get_watchlist_repository

router = APIRouter(prefix="/ml", tags=["ml"])

# In-process job store — keyed by job_id
_jobs: dict[str, dict[str, object]] = {}


def _new_job(job_type: str, symbols: list[str]) -> dict[str, object]:
    job_id = f"{job_type}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}"
    job: dict[str, object] = {
        "job_id":          job_id,
        "type":            job_type,
        "asset_class":     "crypto" if "crypto" in job_type else "stock" if "stock" in job_type else "mixed",
        "symbols":         symbols,
        "status":          "running",
        "started_at":      datetime.now(tz=UTC).isoformat(),
        "finished_at":     None,
        # Progress fields
        "total_symbols":   len(symbols),
        "done_symbols":    0,
        "current_symbol":  None,
        "total_batches":   0,
        "done_batches":    0,
        "rows_fetched":    0,
        "progress_pct":    0,
        "error":           None,
        "result":          None,
    }
    _jobs[job_id] = job
    return job


@router.get("/jobs")
async def list_jobs() -> list[dict[str, object]]:
    """Return all ML job statuses, newest first."""
    return sorted(_jobs.values(), key=lambda j: str(j["started_at"]), reverse=True)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    """Return status for a specific job."""
    if job_id not in _jobs:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


# ── Alpaca top gainers ──────────────────────────────────────────────────

@router.get("/gainers")
async def get_top_gainers(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    """Fetch top gainers from Alpaca screener."""
    settings = get_settings()
    if not settings.alpaca_api_key:
        return {"error": "ALPACA_API_KEY not configured in .env", "gainers": []}

    headers = {
        "APCA-API-KEY-ID":     settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret or "",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://data.alpaca.markets/v1beta1/screener/stocks/movers",
                params={"top": limit, "by": "percent_change"},
                headers=headers,
            )
            if resp.status_code == 401:
                return {"error": "Alpaca API key invalid or unauthorized", "gainers": []}
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"error": f"Alpaca request failed: {exc}", "gainers": []}

    gainers = data.get("gainers", data.get("movers", []))
    return {
        "gainers":    gainers[:limit],
        "count":      len(gainers[:limit]),
        "fetched_at": datetime.now(tz=UTC).isoformat(),
    }


# ── Progress-aware backfill ─────────────────────────────────────────────

async def _run_backfill_with_progress(
    job_id: str,
    symbols: list[str],
    timeframes: list[str],
    lookback_days: int,
    candle_repo: CandleRepository,
) -> None:
    """Background task: batch-fetch OHLCV from Alpaca with per-symbol progress updates."""
    settings = get_settings()
    fetcher = AlpacaTrainingFetcher(
        repository=candle_repo,
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
        lookback_days=lookback_days,
    )

    total_work = len(symbols) * len(timeframes)
    _jobs[job_id]["total_batches"] = total_work
    done_work = 0
    total_rows = 0

    try:
        end = datetime.now(tz=UTC)
        for timeframe in timeframes:
            # Batch symbols per Alpaca limit (200)
            batch_size = fetcher.max_symbols_per_request
            for batch_start in range(0, len(symbols), batch_size):
                batch = symbols[batch_start:batch_start + batch_size]

                # Update progress: show first symbol of batch as current
                _jobs[job_id]["current_symbol"] = f"{batch[0]}…" if len(batch) > 1 else batch[0]
                _jobs[job_id]["done_symbols"]   = batch_start
                _jobs[job_id]["done_batches"]   = done_work
                _jobs[job_id]["progress_pct"]   = int(done_work / total_work * 100) if total_work else 0

                latest_times = await candle_repo.get_latest_candle_times(batch, timeframe, source=ALPACA_DEFAULT_SOURCE)
                start = fetcher._calculate_start(batch, latest_times)
                fetched = await fetcher.fetch_batch(batch, timeframe, start=start, end=end)
                rows = fetcher._rows_from_batch(fetched, timeframe, latest_times)
                if rows:
                    await candle_repo.bulk_upsert(rows)
                    total_rows += len(rows)

                done_work += 1
                _jobs[job_id]["rows_fetched"]  = total_rows
                _jobs[job_id]["done_batches"]  = done_work
                _jobs[job_id]["done_symbols"]  = min(batch_start + batch_size, len(symbols))
                _jobs[job_id]["progress_pct"]  = int(done_work / total_work * 100) if total_work else 0

        _jobs[job_id]["status"]         = "done"
        _jobs[job_id]["current_symbol"] = None
        _jobs[job_id]["progress_pct"]   = 100
        _jobs[job_id]["done_symbols"]   = len(symbols)
        _jobs[job_id]["result"] = {
            "symbols_processed": len(symbols),
            "timeframes":        timeframes,
            "rows_written":      total_rows,
        }
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"]  = str(exc)
    finally:
        _jobs[job_id]["finished_at"] = datetime.now(tz=UTC).isoformat()


@router.post("/backfill/crypto")
async def backfill_crypto(
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    timeframes: str = Query(default="1Day,1Hour"),
    lookback_days: int = Query(default=730, ge=1, le=730),
) -> dict[str, object]:
    """Trigger Alpaca backfill for all 15 Kraken crypto pairs."""
    settings = get_settings()
    if not settings.alpaca_api_key:
        return {"error": "ALPACA_API_KEY not configured in .env"}

    # Alpaca crypto tickers drop the slash: BTC/USD → BTCUSD
    alpaca_symbols = [s.replace("/", "") for s in KRAKEN_UNIVERSE]
    tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
    job = _new_job("backfill_crypto", alpaca_symbols)
    job["asset_class"] = "crypto"
    background_tasks.add_task(
        _run_backfill_with_progress, job["job_id"], alpaca_symbols, tfs, lookback_days, candle_repo
    )
    return job


@router.post("/backfill/stocks")
async def backfill_stocks(
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    symbols: str = Query(description="Comma-separated stock symbols"),
    timeframes: str = Query(default="1Day,1Hour"),
    lookback_days: int = Query(default=730, ge=1, le=730),
) -> dict[str, object]:
    """Trigger Alpaca batch backfill for stock symbols."""
    settings = get_settings()
    if not settings.alpaca_api_key:
        return {"error": "ALPACA_API_KEY not configured in .env"}

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
    job = _new_job("backfill_stocks", sym_list)
    job["asset_class"] = "stock"
    background_tasks.add_task(
        _run_backfill_with_progress, job["job_id"], sym_list, tfs, lookback_days, candle_repo
    )
    return job


@router.post("/backfill/gainers")
async def backfill_gainers(
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    limit: int = Query(default=100, ge=1, le=500),
    timeframes: str = Query(default="1Day"),
    lookback_days: int = Query(default=365, ge=1, le=730),
) -> dict[str, object]:
    """Fetch top gainers then immediately backfill their candles."""
    settings = get_settings()
    if not settings.alpaca_api_key:
        return {"error": "ALPACA_API_KEY not configured in .env"}

    gainers_resp = await get_top_gainers(limit)
    if "error" in gainers_resp:
        return gainers_resp

    gainers = gainers_resp.get("gainers", [])
    syms = [str(g.get("symbol") or g.get("S") or "") for g in gainers]
    syms = [s for s in syms if s][:limit]
    if not syms:
        return {"error": "No gainer symbols returned from Alpaca"}

    tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
    job = _new_job("backfill_gainers", syms)
    job["asset_class"] = "stock"
    job["gainers_snapshot"] = gainers[:limit]
    background_tasks.add_task(
        _run_backfill_with_progress, job["job_id"], syms, tfs, lookback_days, candle_repo
    )
    return job


@router.post("/research/watchlist")
async def trigger_watchlist_research(
    background_tasks: BackgroundTasks,
    watchlist_repo: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> dict[str, object]:
    """Trigger research scoring for all active watchlist symbols."""
    rows = await watchlist_repo.list_active()
    symbols = [r.symbol for r in rows]
    job = _new_job("watchlist_research", symbols)

    async def _run() -> None:
        _jobs[job["job_id"]]["status"]      = "done"
        _jobs[job["job_id"]]["progress_pct"] = 100
        _jobs[job["job_id"]]["finished_at"] = datetime.now(tz=UTC).isoformat()
        _jobs[job["job_id"]]["result"] = {
            "note": "Research pipeline stub — implement app/ml/ session 9",
            "symbols_queued": symbols,
        }

    background_tasks.add_task(_run)
    return job


@router.get("/training/status")
async def training_status() -> dict[str, object]:
    """Return candle counts from alpaca_training source, split by asset class."""
    from sqlalchemy import func, select
    from app.db.session import build_engine, build_session_factory

    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)

    async with factory() as session:
        stmt = (
            select(
                CandleRow.symbol,
                CandleRow.asset_class,
                CandleRow.timeframe,
                func.count().label("count"),
                func.min(CandleRow.time).label("earliest"),
                func.max(CandleRow.time).label("latest"),
            )
            .where(CandleRow.source == ALPACA_DEFAULT_SOURCE)
            .group_by(CandleRow.symbol, CandleRow.asset_class, CandleRow.timeframe)
            .order_by(CandleRow.asset_class, CandleRow.symbol, CandleRow.timeframe)
        )
        result = await session.execute(stmt)
        rows = result.all()

    detail = [
        {
            "symbol":       r.symbol,
            "asset_class":  r.asset_class,
            "timeframe":    r.timeframe,
            "candle_count": r.count,
            "earliest":     r.earliest.isoformat() if r.earliest else None,
            "latest":       r.latest.isoformat() if r.latest else None,
        }
        for r in rows
    ]

    crypto_rows = [d for d in detail if d["asset_class"] == "crypto"]
    stock_rows  = [d for d in detail if d["asset_class"] != "crypto"]

    return {
        "source":              ALPACA_DEFAULT_SOURCE,
        "total_candles":       sum(d["candle_count"] for d in detail),
        "crypto_candles":      sum(d["candle_count"] for d in crypto_rows),
        "stock_candles":       sum(d["candle_count"] for d in stock_rows),
        "crypto_symbols":      len({d["symbol"] for d in crypto_rows}),
        "stock_symbols":       len({d["symbol"] for d in stock_rows}),
        "symbols_with_data":   len({d["symbol"] for d in detail}),
        "crypto_detail":       crypto_rows,
        "stock_detail":        stock_rows,
    }
