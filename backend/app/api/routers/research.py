"""Research data read endpoints for the Research page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_research_repository, get_session
from app.config.crypto_scope import (
    clear_research_crypto_promoted_symbols,
    get_research_crypto_scope_source,
    list_crypto_universe_symbols,
    list_research_crypto_promoted_symbols,
    list_research_crypto_scope_symbols,
    set_research_crypto_promoted_symbols,
)
from app.db.models import CongressTradeRow, InsiderTradeRow, ResearchSignalRow
from app.repositories.research import ResearchRepository
from app.repositories.watchlist import WatchlistRepository

router = APIRouter(prefix="/research", tags=["research"])


class ResearchCryptoWatchlistRequest(BaseModel):
    """Research-only soft crypto watchlist request body."""

    symbols: list[str] = Field(default_factory=list)



@router.get("/scope")
async def get_research_scope(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    """Return backend-truth research scope for stock watchlist and crypto universe."""

    watchlist_repository = WatchlistRepository(session)
    active_rows = await watchlist_repository.list_active()
    stock_rows = [
        row
        for row in active_rows
        if row.asset_class.lower() == "stock"
    ]
    stock_symbols = [row.symbol for row in stock_rows]
    crypto_universe_symbols = list_crypto_universe_symbols()
    crypto_watchlist_symbols = list_research_crypto_scope_symbols()
    promoted_symbols = list_research_crypto_promoted_symbols()

    return {
        "stock_watchlist_symbols": stock_symbols,
        "stock_watchlist_count": len(stock_symbols),
        "stock_watchlist_source": "research watchlist",
        "crypto_universe_symbols": crypto_universe_symbols,
        "crypto_universe_count": len(crypto_universe_symbols),
        "crypto_universe_source": "KRAKEN_UNIVERSE",
        "crypto_watchlist_symbols": crypto_watchlist_symbols,
        "crypto_watchlist_count": len(crypto_watchlist_symbols),
        "crypto_watchlist_source": get_research_crypto_scope_source(),
        "crypto_promoted_symbols": promoted_symbols,
        "crypto_promoted_count": len(promoted_symbols),
        "crypto_promoted_source": "research-only soft watchlist",
    }


@router.put("/crypto-watchlist")
async def set_research_crypto_watchlist(
    request: ResearchCryptoWatchlistRequest,
) -> dict[str, object]:
    """Set Research-only promoted crypto symbols without changing runtime scope."""

    try:
        promoted_symbols = set_research_crypto_promoted_symbols(request.symbols)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scope_symbols = list_research_crypto_scope_symbols()
    return {
        "crypto_promoted_symbols": promoted_symbols,
        "crypto_promoted_count": len(promoted_symbols),
        "crypto_watchlist_symbols": scope_symbols,
        "crypto_watchlist_count": len(scope_symbols),
        "crypto_watchlist_source": get_research_crypto_scope_source(),
        "runtime_scope_changed": False,
    }


@router.delete("/crypto-watchlist")
async def clear_research_crypto_watchlist() -> dict[str, object]:
    """Clear Research-only promoted crypto symbols and restore universe fallback."""

    clear_research_crypto_promoted_symbols()
    scope_symbols = list_research_crypto_scope_symbols()
    return {
        "crypto_promoted_symbols": [],
        "crypto_promoted_count": 0,
        "crypto_watchlist_symbols": scope_symbols,
        "crypto_watchlist_count": len(scope_symbols),
        "crypto_watchlist_source": get_research_crypto_scope_source(),
        "runtime_scope_changed": False,
    }


@router.get("/signals")
async def list_signals(
    repository: Annotated[ResearchRepository, Depends(get_research_repository)],
    symbol: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    """Return recent research signals for a symbol."""

    rows = await repository.list_signals(symbol, limit=limit)
    return [_serialize_signal(row) for row in rows]


@router.get("/congress")
async def list_congress_trades(
    repository: Annotated[ResearchRepository, Depends(get_research_repository)],
    symbol: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    """Return recent congressional trades for a symbol."""

    rows = await repository.list_congress_trades(symbol, limit=limit)
    return [_serialize_congress(row) for row in rows]


@router.get("/insider")
async def list_insider_trades(
    repository: Annotated[ResearchRepository, Depends(get_research_repository)],
    symbol: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    """Return recent insider trades for a symbol."""

    rows = await repository.list_insider_trades(symbol, limit=limit)
    return [_serialize_insider(row) for row in rows]


def _serialize_signal(row: ResearchSignalRow) -> dict[str, object]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "signal_type": row.signal_type,
        "score": float(row.score) if row.score is not None else None,
        "direction": row.direction,
        "source": row.source,
        "raw_data": row.raw_data,
        "created_at": row.created_at.isoformat(),
    }


def _serialize_congress(row: CongressTradeRow) -> dict[str, object]:
    return {
        "id": row.id,
        "politician": row.politician,
        "chamber": row.chamber,
        "symbol": row.symbol,
        "trade_type": row.trade_type,
        "amount_range": row.amount_range,
        "trade_date": row.trade_date.isoformat() if row.trade_date is not None else None,
        "disclosure_date": (
            row.disclosure_date.isoformat() if row.disclosure_date is not None else None
        ),
        "days_to_disclose": row.days_to_disclose,
        "created_at": row.created_at.isoformat(),
    }


def _serialize_insider(row: InsiderTradeRow) -> dict[str, object]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "insider_name": row.insider_name,
        "title": row.title,
        "transaction_type": row.transaction_type,
        "total_value": float(row.total_value) if row.total_value is not None else None,
        "filing_date": row.filing_date.isoformat() if row.filing_date is not None else None,
        "transaction_date": (
            row.transaction_date.isoformat() if row.transaction_date is not None else None
        ),
    }