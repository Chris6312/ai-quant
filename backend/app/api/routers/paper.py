"""Paper trading ledger — balance controls and order log."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict, cast

from fastapi import APIRouter, Query

router = APIRouter(prefix="/paper", tags=["paper"])


class PaperOrder(TypedDict):
    """Typed paper-order record stored in the in-process ledger."""

    id: str
    symbol: str
    asset_class: str
    side: str
    size: float
    price: float
    gross: float
    commission: float
    strategy_id: str | None
    source: str
    created_at: str


class PaperLedger(TypedDict):
    """Typed in-process paper ledger."""

    stock_balance: float
    crypto_balance: float
    stock_default: float
    crypto_default: float
    realized_pnl: float
    orders: list[PaperOrder]


_ledger: PaperLedger = {
    "stock_balance": 100_000.0,
    "crypto_balance": 100_000.0,
    "stock_default": 100_000.0,
    "crypto_default": 100_000.0,
    "realized_pnl": 0.0,
    "orders": [],
}


@router.get("/balance")
async def get_paper_balance() -> dict[str, object]:
    """Return current paper ledger balances."""

    return {
        "stock_balance": _ledger["stock_balance"],
        "crypto_balance": _ledger["crypto_balance"],
        "stock_default": _ledger["stock_default"],
        "crypto_default": _ledger["crypto_default"],
        "realized_pnl": _ledger["realized_pnl"],
        "nav": _ledger["stock_balance"] + _ledger["crypto_balance"],
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

    orders = list(_ledger["orders"])

    if side:
        orders = [o for o in orders if o.get("side") == side]
    if symbol:
        normalized_symbol = symbol.upper()
        orders = [o for o in orders if o.get("symbol", "").upper() == normalized_symbol]
    if date_from:
        orders = [o for o in orders if str(o.get("created_at", "")) >= date_from]
    if date_to:
        orders = [o for o in orders if str(o.get("created_at", "")) <= date_to + "T23:59:59"]

    return cast(list[dict[str, object]], sorted(
        orders,
        key=lambda o: str(o.get("created_at", "")),
        reverse=True,
    ))


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

    if asset_class == "crypto":
        if side == "buy":
            _ledger["crypto_balance"] = _ledger["crypto_balance"] - gross - commission
        else:
            _ledger["crypto_balance"] = _ledger["crypto_balance"] + gross - commission
            _ledger["realized_pnl"] = _ledger["realized_pnl"] + gross - commission
    else:
        if side == "buy":
            _ledger["stock_balance"] = _ledger["stock_balance"] - gross - commission
        else:
            _ledger["stock_balance"] = _ledger["stock_balance"] + gross - commission
            _ledger["realized_pnl"] = _ledger["realized_pnl"] + gross - commission

    order: PaperOrder = {
        "id": f"paper-{len(_ledger['orders']) + 1:06d}",
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
    _ledger["orders"].append(order)
    return cast(dict[str, object], order)
