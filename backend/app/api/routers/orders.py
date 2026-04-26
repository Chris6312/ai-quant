"""Order log endpoints — paper and live order history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_paper_ledger_service, get_position_repository
from app.db.models import PaperOrderRow, PositionRow
from app.paper.ledger_service import PaperLedgerService
from app.repositories.positions import PositionRepository

router = APIRouter(prefix="/orders", tags=["orders"])


def _serialize_position(row: PositionRow, source: str = "live") -> dict[str, object]:
    """Convert a position row into an order-log entry."""

    entry_val = float(row.entry_price) * float(row.size) if row.entry_price and row.size else None
    return {
        "id": row.id,
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "side": row.side,
        "entry_price": float(row.entry_price) if row.entry_price else None,
        "size": float(row.size) if row.size else None,
        "entry_value": round(entry_val, 4) if entry_val else None,
        "sl_price": float(row.sl_price) if row.sl_price else None,
        "tp_price": float(row.tp_price) if row.tp_price else None,
        "strategy_id": row.strategy_id,
        "ml_confidence": row.ml_confidence,
        "research_score": float(row.research_score) if row.research_score else None,
        "status": row.status,
        "source": source,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
    }


def _serialize_paper_order(row: PaperOrderRow) -> dict[str, object]:
    """Convert a durable paper order row into an order-log entry."""

    entry_val = (
        float(row.average_fill_price) * float(row.filled_size)
        if row.average_fill_price
        else None
    )
    return {
        "id": row.id,
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "side": row.side,
        "entry_price": None if row.average_fill_price is None else float(row.average_fill_price),
        "size": float(row.filled_size),
        "entry_value": round(entry_val, 4) if entry_val is not None else None,
        "sl_price": None,
        "tp_price": None,
        "strategy_id": row.strategy_id,
        "ml_confidence": None,
        "research_score": None,
        "status": row.status,
        "source": row.source,
        "opened_at": row.created_at.isoformat(),
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("")
async def list_orders(
    position_repository: Annotated[PositionRepository, Depends(get_position_repository)],
    paper_ledger: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    source: str = Query(default="all", description="'live' | 'paper' | 'all'"),
    status: str | None = Query(default=None, description="'open' | 'closed'"),
    symbol: str | None = Query(default=None),
    asset_class: str | None = Query(default=None, description="'stock' | 'crypto'"),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, object]]:
    """Return filtered order/position log from the database."""

    results: list[dict[str, object]] = []

    if source in ("live", "all"):
        rows = await position_repository.list_all()
        for row in rows:
            if status and row.status != status:
                continue
            if symbol and row.symbol.upper() != symbol.upper():
                continue
            if asset_class and row.asset_class != asset_class:
                continue
            if date_from and row.opened_at and row.opened_at.date().isoformat() < date_from:
                continue
            if date_to and row.opened_at and row.opened_at.date().isoformat() > date_to:
                continue

            results.append(_serialize_position(row, source="live"))

    if source in ("paper", "all"):
        paper_orders = await paper_ledger.list_orders(symbol=symbol)
        for order in paper_orders:
            if status and order.status != status:
                continue
            if asset_class and order.asset_class != asset_class:
                continue
            created_date = order.created_at.date().isoformat()
            if date_from and created_date < date_from:
                continue
            if date_to and created_date > date_to:
                continue

            results.append(_serialize_paper_order(order))

    results.sort(key=lambda r: str(r.get("opened_at") or r.get("created_at") or ""), reverse=True)
    return results[:limit]


@router.get("/export")
async def export_orders_csv(
    position_repository: Annotated[PositionRepository, Depends(get_position_repository)],
    paper_ledger: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    source: str = Query(default="all"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> StreamingResponse:
    """Export order log as a CSV file download."""

    orders = await list_orders(
        position_repository=position_repository,
        paper_ledger=paper_ledger,
        source=source,
        status=None,
        symbol=None,
        asset_class=None,
        date_from=date_from,
        date_to=date_to,
        limit=10000,
    )

    headers_row = [
        "id",
        "symbol",
        "asset_class",
        "side",
        "entry_price",
        "size",
        "entry_value",
        "strategy_id",
        "status",
        "source",
        "opened_at",
        "closed_at",
    ]

    def row_to_csv(order: dict[str, object]) -> str:
        vals = [str(order.get(h, "") or "") for h in headers_row]
        return ",".join(f'"{v}"' for v in vals)

    lines = [",".join(headers_row)] + [row_to_csv(o) for o in orders]
    csv_content = "\n".join(lines) + "\n"

    filename = f"orders_{source}_{datetime.now(tz=UTC).strftime('%Y%m%d')}"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
    )