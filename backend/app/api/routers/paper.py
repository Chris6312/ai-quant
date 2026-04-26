"""Paper trading ledger API backed by durable database state."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_paper_ledger_service
from app.db.models import PaperAccountRow, PaperFillRow, PaperOrderRow, PaperPositionRow
from app.paper.ledger_service import PaperExecutionResult, PaperLedgerService

router = APIRouter(prefix="/paper", tags=["paper"])


def _iso(value: datetime | None) -> str | None:
    """Serialize datetimes consistently for paper API responses."""

    if value is None:
        return None
    return value.isoformat()


def _account_payload(account: PaperAccountRow) -> dict[str, object]:
    """Convert a durable paper account row into API output."""

    return {
        "id": account.id,
        "asset_class": account.asset_class,
        "cash_balance": float(account.cash_balance),
        "default_cash_balance": float(account.default_cash_balance),
        "realized_pnl": float(account.realized_pnl),
        "reset_count": account.reset_count,
        "last_reset_at": _iso(account.last_reset_at),
        "created_at": _iso(account.created_at),
        "updated_at": _iso(account.updated_at),
    }


def _position_payload(position: PaperPositionRow) -> dict[str, object]:
    """Convert a durable paper position row into API output."""

    return {
        "id": position.id,
        "symbol": position.symbol,
        "asset_class": position.asset_class,
        "side": position.side,
        "size": float(position.size),
        "average_entry_price": float(position.average_entry_price),
        "realized_pnl": float(position.realized_pnl),
        "status": position.status,
        "strategy_id": position.strategy_id,
        "opened_at": _iso(position.opened_at),
        "updated_at": _iso(position.updated_at),
        "closed_at": _iso(position.closed_at),
    }


def _order_payload(order: PaperOrderRow) -> dict[str, object]:
    """Convert a durable paper order row into API output."""

    return {
        "id": order.id,
        "symbol": order.symbol,
        "asset_class": order.asset_class,
        "side": order.side,
        "order_type": order.order_type,
        "requested_size": float(order.requested_size),
        "limit_price": None if order.limit_price is None else float(order.limit_price),
        "status": order.status,
        "filled_size": float(order.filled_size),
        "average_fill_price": (
            None if order.average_fill_price is None else float(order.average_fill_price)
        ),
        "remaining_size": float(order.remaining_size),
        "strategy_id": order.strategy_id,
        "source": order.source,
        "reject_reason": order.reject_reason,
        "created_at": _iso(order.created_at),
        "updated_at": _iso(order.updated_at),
        "closed_at": _iso(order.closed_at),
    }


def _fill_payload(fill: PaperFillRow) -> dict[str, object]:
    """Convert a durable paper fill row into API output."""

    return {
        "id": fill.id,
        "order_id": fill.order_id,
        "position_id": fill.position_id,
        "symbol": fill.symbol,
        "asset_class": fill.asset_class,
        "side": fill.side,
        "fill_size": float(fill.fill_size),
        "fill_price": float(fill.fill_price),
        "gross": float(fill.gross),
        "commission": float(fill.commission),
        "realized_pnl": float(fill.realized_pnl),
        "cash_after": float(fill.cash_after),
        "source": fill.source,
        "filled_at": _iso(fill.filled_at),
    }


def _balance_payload(accounts: list[PaperAccountRow]) -> dict[str, object]:
    """Build the legacy-compatible paper balance payload from durable accounts."""

    by_asset = {account.asset_class: account for account in accounts}
    stock = by_asset.get("stock")
    crypto = by_asset.get("crypto")
    stock_balance = 0.0 if stock is None else float(stock.cash_balance)
    crypto_balance = 0.0 if crypto is None else float(crypto.cash_balance)
    stock_default = 0.0 if stock is None else float(stock.default_cash_balance)
    crypto_default = 0.0 if crypto is None else float(crypto.default_cash_balance)
    realized_pnl = sum(float(account.realized_pnl) for account in accounts)
    return {
        "stock_balance": stock_balance,
        "crypto_balance": crypto_balance,
        "stock_default": stock_default,
        "crypto_default": crypto_default,
        "realized_pnl": realized_pnl,
        "nav": stock_balance + crypto_balance,
        "accounts": [_account_payload(account) for account in accounts],
        "source": "database",
    }


def _execution_payload(result: PaperExecutionResult) -> dict[str, object]:
    """Build API output for a durable market-fill execution."""

    return {
        "order": _order_payload(result.order),
        "fill": _fill_payload(result.fill),
        "position": None if result.position is None else _position_payload(result.position),
        "account": _account_payload(result.account),
        "source": "database",
    }


@router.get("/balance")
async def get_paper_balance(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
) -> dict[str, object]:
    """Return current durable paper ledger balances."""

    accounts = await service.list_accounts()
    return _balance_payload(accounts)


@router.get("/state")
async def get_paper_state(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
) -> dict[str, object]:
    """Return durable paper accounts, open positions, orders, and fills."""

    accounts = await service.list_accounts()
    positions = await service.list_open_positions()
    orders = await service.list_orders()
    fills = await service.list_fills()
    return {
        "balance": _balance_payload(accounts),
        "positions": [_position_payload(position) for position in positions],
        "orders": [_order_payload(order) for order in orders],
        "fills": [_fill_payload(fill) for fill in fills],
        "source": "database",
    }


@router.post("/balance/set")
async def set_paper_balance(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    stock: float | None = Query(default=None, ge=0, description="New stock balance"),
    crypto: float | None = Query(default=None, ge=0, description="New crypto balance"),
) -> dict[str, object]:
    """Set durable paper stock and/or crypto balances."""

    if stock is None and crypto is None:
        raise HTTPException(status_code=400, detail="provide stock and/or crypto balance")
    if stock is not None:
        await service.set_account_balance("stock", stock)
    if crypto is not None:
        await service.set_account_balance("crypto", crypto)
    accounts = await service.list_accounts()
    return _balance_payload(accounts)


@router.post("/balance/reset")
async def reset_paper_balance(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    asset_class: str = Query(description="'stock' | 'crypto' | 'all'"),
) -> dict[str, object]:
    """Reset durable paper balance back to the configured default."""

    try:
        await service.reset_account(asset_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    accounts = await service.list_accounts()
    return _balance_payload(accounts)


@router.get("/positions")
async def list_paper_positions(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    asset_class: str | None = Query(default=None, description="'stock' | 'crypto'"),
) -> list[dict[str, object]]:
    """Return durable open paper positions."""

    positions = await service.list_open_positions(asset_class=asset_class)
    return [_position_payload(position) for position in positions]


@router.get("/orders")
async def list_paper_orders(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    side: str | None = Query(default=None, description="'buy' | 'sell'"),
    symbol: str | None = Query(default=None),
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
) -> list[dict[str, object]]:
    """Return durable paper order log, optionally filtered."""

    orders = await service.list_orders(symbol=symbol)
    if side is not None:
        orders = [order for order in orders if order.side == side]
    if date_from is not None:
        orders = [order for order in orders if order.created_at.isoformat() >= date_from]
    if date_to is not None:
        upper_bound = f"{date_to}T23:59:59"
        orders = [order for order in orders if order.created_at.isoformat() <= upper_bound]
    return [_order_payload(order) for order in orders]


@router.get("/fills")
async def list_paper_fills(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    symbol: str | None = Query(default=None),
) -> list[dict[str, object]]:
    """Return durable paper fills for audit and restart verification."""

    fills = await service.list_fills(symbol=symbol)
    return [_fill_payload(fill) for fill in fills]


@router.post("/orders/add")
async def add_paper_order(
    service: Annotated[PaperLedgerService, Depends(get_paper_ledger_service)],
    symbol: str = Query(min_length=1),
    side: str = Query(description="'buy' | 'sell'"),
    size: float = Query(gt=0),
    price: float = Query(gt=0),
    asset_class: str = Query(default="stock", description="'stock' | 'crypto'"),
    strategy_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Record a simulated paper fill through the durable ledger service."""

    try:
        result = await service.execute_market_fill(
            symbol=symbol,
            asset_class=asset_class,
            side=side,
            size=size,
            fill_price=price,
            strategy_id=strategy_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _execution_payload(result)
