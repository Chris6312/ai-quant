"""Paper trading ledger — balance controls and order log."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_candle_repository, get_session
from app.config.constants import APP_NAME
from app.db.models import CandleRow
from app.repositories.candles import CandleRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/paper", tags=["paper"])

# In-process ledger state — survives for the life of the process.
# A real implementation would persist to the trades / portfolio_snapshots tables.
_ledger: dict[str, object] = {
    "stock_balance": 100_000.0,
    "crypto_balance": 100_000.0,
    "stock_default": 100_000.0,
    "crypto_default": 100_000.0,
    "realized_pnl": 0.0,
    "orders": [],          # list[dict] — appended by submit_paper_order
}


@router.get("/balance")
async def get_paper_balance() -> dict[str, object]:
    """Return current paper ledger balances."""

    return {
        "stock_balance":  _ledger["stock_balance"],
        "crypto_balance": _ledger["crypto_balance"],
        "stock_default":  _ledger["stock_default"],
        "crypto_default": _ledger["crypto_default"],
        "realized_pnl":   _ledger["realized_pnl"],
        "nav": float(_ledger["stock_balance"]) + float(_ledger["crypto_balance"]),  # type: ignore[arg-type]
    }


@router.post("/balance/set")
async def set_paper_balance(
    stock: float | None = Query(default=None, ge=0, description="New stock balance"),
    crypto: float | None = Query(default=None, ge=0, description="New crypto balance"),
) -> dict[str, object]:
    """Set paper stock and/or crypto balance to a custom value."""

    if stock is not None:
        _ledger["stock_balance"] = stock
        _ledger["stock_default"] = stock
    if crypto is not None:
        _ledger["crypto_balance"] = crypto
        _ledger["crypto_default"] = crypto
    return await get_paper_balance()


@router.post("/balance/reset")
async def reset_paper_balance(
    asset_class: str = Query(description="'stock' | 'crypto' | 'all'"),
) -> dict[str, object]:
    """Reset paper balance back to the configured default."""

    if asset_class in ("stock", "all"):
        _ledger["stock_balance"] = _ledger["stock_default"]
    if asset_class in ("crypto", "all"):
        _ledger["crypto_balance"] = _ledger["crypto_default"]
    if asset_class == "all":
        _ledger["realized_pnl"] = 0.0
        _ledger["orders"] = []
    return await get_paper_balance()


@router.get("/orders")
async def list_paper_orders(
    side: str | None = Query(default=None, description="'buy' | 'sell'"),
    symbol: str | None = Query(default=None),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
) -> list[dict[str, object]]:
    """Return paper order log, optionally filtered."""

    orders: list[dict[str, object]] = list(_ledger["orders"])  # type: ignore[arg-type]

    if side:
        orders = [o for o in orders if o.get("side") == side]
    if symbol:
        orders = [o for o in orders if o.get("symbol", "").upper() == symbol.upper()]
    if date_from:
        orders = [o for o in orders if str(o.get("created_at", "")) >= date_from]
    if date_to:
        orders = [o for o in orders if str(o.get("created_at", "")) <= date_to + "T23:59:59"]

    return sorted(orders, key=lambda o: str(o.get("created_at", "")), reverse=True)


@router.post("/orders/add")
async def add_paper_order(
    symbol: str = Query(min_length=1),
    side: str = Query(description="'buy' | 'sell'"),
    size: float = Query(gt=0),
    price: float = Query(gt=0),
    asset_class: str = Query(default="stock", description="'stock' | 'crypto'"),
    strategy_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Record a simulated paper order and update the ledger balance."""

    gross = size * price
    commission = gross * 0.0016 if asset_class == "crypto" else 0.0

    if side == "buy":
        key = "crypto_balance" if asset_class == "crypto" else "stock_balance"
        _ledger[key] = float(_ledger[key]) - gross - commission  # type: ignore[arg-type]
    else:
        key = "crypto_balance" if asset_class == "crypto" else "stock_balance"
        _ledger[key] = float(_ledger[key]) + gross - commission  # type: ignore[arg-type]
        _ledger["realized_pnl"] = float(_ledger["realized_pnl"]) + gross - commission  # type: ignore[arg-type]

    order: dict[str, object] = {
        "id": f"paper-{len(_ledger['orders']) + 1:06d}",  # type: ignore[arg-type]
        "symbol": symbol.upper(),
        "asset_class": asset_class,
        "side": side,
        "size": size,
        "price": price,
        "gross": gross,
        "commission": commission,
        "strategy_id": strategy_id,
        "source": "paper",
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    _ledger["orders"].append(order)  # type: ignore[union-attr]
    return order
