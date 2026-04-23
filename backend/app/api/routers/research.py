"""Research data read endpoints for the Research page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_research_repository, get_session
from app.config.crypto_scope import (
    list_crypto_universe_symbols,
    list_crypto_watchlist_symbols,
)
from app.db.models import CongressTradeRow, InsiderTradeRow, ResearchSignalRow
from app.repositories.research import ResearchRepository
from app.repositories.watchlist import WatchlistRepository

router = APIRouter(prefix="/research", tags=["research"])


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
    crypto_watchlist_symbols = list_crypto_watchlist_symbols()

    return {
        "stock_watchlist_symbols": stock_symbols,
        "stock_watchlist_count": len(stock_symbols),
        "stock_watchlist_source": "research watchlist",
        "crypto_universe_symbols": crypto_universe_symbols,
        "crypto_universe_count": len(crypto_universe_symbols),
        "crypto_universe_source": "KRAKEN_UNIVERSE",
        "crypto_watchlist_symbols": crypto_watchlist_symbols,
        "crypto_watchlist_count": len(crypto_watchlist_symbols),
        "crypto_watchlist_source": "crypto universe",
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