"""Machine learning and research pipeline triggers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.dependencies import (
    get_candle_repository,
    get_research_repository,
    get_watchlist_repository,
)
from app.brokers.alpaca import AlpacaTrainingFetcher
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.config.constants import ALPACA_DEFAULT_SOURCE
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.db.session import build_engine, build_session_factory
from app.repositories.candles import CandleRepository
from app.repositories.research import ResearchRepository
from app.repositories.watchlist import WatchlistRepository
from app.research.models import (
    AnalystRating,
    AnalystRatingPayload,
    CongressTrade,
    CongressTradePayload,
    InsiderTrade,
    InsiderTradePayload,
    NewsArticle,
    NewsArticlePayload,
    ScreeningMetrics,
    ScreeningMetricsPayload,
)
from app.research.news_sentiment import NewsSentimentPipeline
from app.research.orchestrator import ResearchOrchestrator
from app.research.scorer import WatchlistScorer
from app.research.screener import StockScreenerService

router = APIRouter(prefix="/ml", tags=["ml"])

# In-process job store — keyed by job_id
_jobs: dict[str, dict[str, Any]] = {}


def _resolve_asset_class(job_type: str) -> str:
    if "crypto" in job_type:
        return "crypto"
    if "stock" in job_type:
        return "stock"
    return "mixed"


def _new_job(job_type: str, symbols: list[str]) -> dict[str, Any]:
    job_id = f"{job_type}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}"
    job: dict[str, Any] = {
        "job_id":          job_id,
        "type":            job_type,
        "asset_class":     _resolve_asset_class(job_type),
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
                "https://data.alpaca.markets/v1beta1/screener/stocks/most-actives",
                params={"top": limit, "by": "volume"},
                headers=headers,
            )
            if resp.status_code == 401:
                return {"error": "Alpaca API key invalid or unauthorized", "gainers": []}
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"error": f"Alpaca request failed: {exc}", "gainers": []}

    gainers = data.get("most-actives", data.get("actives", data.get("data",[])))
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
                progress_pct = int(done_work / total_work * 100) if total_work else 0
                _jobs[job_id]["progress_pct"] = progress_pct

                latest_times = await candle_repo.get_latest_candle_times(
                    batch,
                    timeframe,
                    source=ALPACA_DEFAULT_SOURCE,
                )
                start = fetcher._calculate_start(batch, latest_times)
                fetched = await fetcher.fetch_batch(batch, timeframe, start=start, end=end)
                rows = fetcher._rows_from_batch(fetched, timeframe)
                if rows:
                    await candle_repo.bulk_upsert(rows)
                    total_rows += len(rows)

                done_work += 1
                _jobs[job_id]["rows_fetched"]  = total_rows
                _jobs[job_id]["done_batches"]  = done_work
                _jobs[job_id]["done_symbols"]  = min(batch_start + batch_size, len(symbols))
                progress_pct = int(done_work / total_work * 100) if total_work else 0
                _jobs[job_id]["progress_pct"] = progress_pct

        _jobs[job_id]["status"]         = "done"
        _jobs[job_id]["current_symbol"] = None
        _jobs[job_id]["progress_pct"]   = 100
        _jobs[job_id]["done_symbols"]   = len(symbols)
        _jobs[job_id]["result"] = {
            "symbols_processed": len(symbols),
            "timeframes":        timeframes,
            "rows_written":      total_rows,
        }
    except Exception as exc:
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
        _run_backfill_with_progress,
        cast(str, job["job_id"]),
        alpaca_symbols,
        tfs,
        lookback_days,
        candle_repo,
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
        _run_backfill_with_progress,
        cast(str, job["job_id"]),
        sym_list,
        tfs,
        lookback_days,
        candle_repo,
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

    gainers = cast(list[dict[str, object]], gainers_resp.get("gainers", []))
    syms = [str(g.get("symbol") or g.get("S") or "") for g in gainers]
    syms = [s for s in syms if s][:limit]
    if not syms:
        return {"error": "No gainer symbols returned from Alpaca"}

    tfs = [t.strip() for t in timeframes.split(",") if t.strip()]
    job = _new_job("backfill_gainers", syms)
    job["asset_class"] = "stock"
    job["gainers_snapshot"] = gainers[:limit]
    background_tasks.add_task(
        _run_backfill_with_progress,
        cast(str, job["job_id"]),
        syms,
        tfs,
        lookback_days,
        candle_repo,
    )
    return job


class ResearchTriggerRequest(BaseModel):
    """Optional manual payloads for a Phase 2 research run."""

    news: list[NewsArticlePayload] = []
    congress: list[CongressTradePayload] = []
    insider: list[InsiderTradePayload] = []
    screener: list[ScreeningMetricsPayload] = []
    analyst: list[AnalystRatingPayload] = []
    seed_symbols: list[str] = []


@router.post("/research/watchlist")
async def trigger_watchlist_research(
    payload: ResearchTriggerRequest,
    watchlist_repo: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
    research_repo: Annotated[ResearchRepository, Depends(get_research_repository)],
) -> dict[str, object]:
    """Trigger research scoring using persisted data plus optional manual payloads."""

    rows = await watchlist_repo.list_active()
    symbols = sorted({r.symbol for r in rows} | {symbol.upper() for symbol in payload.seed_symbols})
    job = _new_job("watchlist_research", symbols)
    job_id = cast(str, job["job_id"])

    news_articles = [
        NewsArticle(
            symbol=item.symbol.upper(),
            title=item.title,
            summary=item.summary,
            published_at=item.published_at,
            source=item.source,
        )
        for item in payload.news
    ]
    congress_trades = [
        CongressTrade(
            symbol=item.symbol.upper(),
            trade_type=item.trade_type.lower(),
            chamber=item.chamber,
            days_to_disclose=item.days_to_disclose,
            politician=item.politician,
            committee=item.committee,
            amount_range=item.amount_range,
            trade_date=item.trade_date,
            disclosure_date=item.disclosure_date,
        )
        for item in payload.congress
    ]
    insider_trades = [
        InsiderTrade(
            symbol=item.symbol.upper(),
            insider_name=item.insider_name,
            title=item.title,
            transaction_type=item.transaction_type.upper(),
            total_value=item.total_value,
            filing_date=item.filing_date,
            transaction_date=item.transaction_date,
        )
        for item in payload.insider
    ]
    screener_metrics = [
        ScreeningMetrics(
            symbol=item.symbol.upper(),
            avg_volume=item.avg_volume,
            price=item.price,
            market_cap=item.market_cap,
            pe_ratio=item.pe_ratio,
            relative_volume=item.relative_volume,
            float_shares=item.float_shares,
            sector=item.sector,
            above_50d_ema=item.above_50d_ema,
            earnings_blocked=item.earnings_blocked,
        )
        for item in payload.screener
    ]
    analyst_ratings = [
        AnalystRating(
            symbol=item.symbol.upper(),
            firm=item.firm,
            action=item.action,
            current_price=item.current_price,
            old_price_target=item.old_price_target,
            new_price_target=item.new_price_target,
            rating=item.rating,
            published_at=item.published_at,
        )
        for item in payload.analyst
    ]

    try:
        orchestrator = ResearchOrchestrator(
            research_repository=research_repo,
            watchlist_repository=watchlist_repo,
            news_pipeline=NewsSentimentPipeline(),
            screener_service=StockScreenerService(),
            scorer=WatchlistScorer(),
        )
        result = await orchestrator.run_manual_research(
            news_articles=news_articles,
            congress_trades=congress_trades,
            insider_trades=insider_trades,
            screener_metrics=screener_metrics,
            analyst_ratings=analyst_ratings,
            seed_symbols=payload.seed_symbols,
        )
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["progress_pct"] = 100
        _jobs[job_id]["done_symbols"] = len(result.symbols_scored)
        _jobs[job_id]["finished_at"] = datetime.now(tz=UTC).isoformat()
        _jobs[job_id]["result"] = {
            "symbols_scored": result.symbols_scored,
            "promoted_symbols": result.promoted_symbols,
            "demoted_symbols": result.demoted_symbols,
            "persisted_signal_count": result.persisted_signal_count,
            "top_breakdowns": [
                {
                    "symbol": breakdown.symbol,
                    "composite_score": breakdown.composite_score,
                }
                for breakdown in result.breakdowns[:10]
            ],
        }
    except Exception as exc:  # pragma: no cover - defensive boundary
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(exc)
        _jobs[job_id]["finished_at"] = datetime.now(tz=UTC).isoformat()
    return job


@router.get("/training/status")
async def training_status() -> dict[str, object]:
    """Return candle counts from alpaca_training source, split by asset class."""
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
