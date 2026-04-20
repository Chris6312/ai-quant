"""Watchlist endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_watchlist_repository
from app.db.models import WatchlistRow
from app.repositories.watchlist import WatchlistRepository

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
async def list_watchlist(
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> list[dict[str, object]]:
    """Return the active watchlist."""

    rows = await repository.list_active()
    return [_serialize_watchlist(row) for row in rows]


def _serialize_watchlist(row: WatchlistRow) -> dict[str, object]:
    """Convert a watchlist row to an API payload."""

    return {
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "added_at": row.added_at.isoformat(),
        "added_by": row.added_by,
        "research_score": float(row.research_score) if row.research_score is not None else None,
        "is_active": row.is_active,
        "notes": row.notes,
    }
