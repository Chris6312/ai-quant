"""Service layer for durable paper ledger operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.db.models import PaperAccountRow, PaperFillRow, PaperOrderRow, PaperPositionRow

DEFAULT_PAPER_BALANCE = 100_000.0
CRYPTO_COMMISSION_RATE = 0.0016
STOCK_COMMISSION_RATE = 0.0


class PaperLedgerStore(Protocol):
    """Persistence boundary required by the paper ledger service."""

    async def get_or_create_account(
        self,
        asset_class: str,
        default_cash_balance: float,
    ) -> PaperAccountRow:
        """Return an existing account or persist a default one."""

    async def set_account_balance(
        self,
        asset_class: str,
        cash_balance: float,
        default_cash_balance: float | None = None,
    ) -> PaperAccountRow:
        """Persist account cash balance changes."""

    async def list_open_positions(self, asset_class: str | None = None) -> list[PaperPositionRow]:
        """Return persisted open paper positions."""

    async def get_open_position(self, symbol: str) -> PaperPositionRow | None:
        """Return a persisted open position for a symbol."""

    async def create_position(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        size: float,
        average_entry_price: float,
        strategy_id: str | None = None,
    ) -> PaperPositionRow:
        """Persist a new open paper position."""

    async def update_position_size(
        self,
        position: PaperPositionRow,
        size: float,
        average_entry_price: float,
    ) -> PaperPositionRow:
        """Persist an open position quantity update."""

    async def close_position(
        self,
        position: PaperPositionRow,
        realized_pnl: float,
    ) -> PaperPositionRow:
        """Persist a closed paper position."""

    async def create_order(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        order_type: str,
        requested_size: float,
        limit_price: float | None = None,
        strategy_id: str | None = None,
        status: str = "submitted",
    ) -> PaperOrderRow:
        """Persist a paper order."""

    async def update_order_fill_state(
        self,
        order: PaperOrderRow,
        filled_size: float,
        average_fill_price: float,
        status: str,
    ) -> PaperOrderRow:
        """Persist paper order fill state."""

    async def create_fill(
        self,
        order_id: str,
        position_id: str | None,
        symbol: str,
        asset_class: str,
        side: str,
        fill_size: float,
        fill_price: float,
        commission: float,
        realized_pnl: float,
        cash_after: float,
    ) -> PaperFillRow:
        """Persist an immutable fill event."""


@dataclass(frozen=True, slots=True)
class PaperLedgerSnapshot:
    """Durable paper account state restored from the database."""

    stock_cash: float
    crypto_cash: float
    open_positions: tuple[PaperPositionRow, ...]


@dataclass(frozen=True, slots=True)
class PaperExecutionResult:
    """Result of a durable paper order execution."""

    order: PaperOrderRow
    fill: PaperFillRow
    position: PaperPositionRow | None
    account: PaperAccountRow


class PaperLedgerService:
    """Coordinate durable paper account, position, order, and fill updates."""

    def __init__(self, store: PaperLedgerStore) -> None:
        self.store = store

    async def restore_snapshot(self) -> PaperLedgerSnapshot:
        """Restore balances and open positions from durable database state."""

        stock_account = await self.store.get_or_create_account("stock", DEFAULT_PAPER_BALANCE)
        crypto_account = await self.store.get_or_create_account("crypto", DEFAULT_PAPER_BALANCE)
        open_positions = await self.store.list_open_positions()
        return PaperLedgerSnapshot(
            stock_cash=float(stock_account.cash_balance),
            crypto_cash=float(crypto_account.cash_balance),
            open_positions=tuple(open_positions),
        )

    async def execute_market_fill(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        size: float,
        fill_price: float,
        strategy_id: str | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> PaperExecutionResult:
        """Persist an order, fill, account update, and position update atomically enough."""

        self._validate_fill_request(side, size, fill_price)
        normalized_symbol = symbol.upper()
        account = await self.store.get_or_create_account(asset_class, DEFAULT_PAPER_BALANCE)
        order = await self.store.create_order(
            symbol=normalized_symbol,
            asset_class=asset_class,
            side=side,
            order_type=order_type,
            requested_size=size,
            limit_price=limit_price,
            strategy_id=strategy_id,
            status="submitted",
        )
        gross = size * fill_price
        commission = self._commission(asset_class, gross)
        realized_pnl = 0.0
        position = await self.store.get_open_position(normalized_symbol)

        if side == "buy":
            cash_after = float(account.cash_balance) - gross - commission
            position = await self._apply_buy_position(
                position=position,
                symbol=normalized_symbol,
                asset_class=asset_class,
                size=size,
                fill_price=fill_price,
                strategy_id=strategy_id,
            )
        else:
            if position is None:
                raise ValueError("cannot sell without an open durable paper position")
            realized_pnl = (fill_price - float(position.average_entry_price)) * size - commission
            cash_after = float(account.cash_balance) + gross - commission
            position = await self._apply_sell_position(position, size, realized_pnl)

        account = await self.store.set_account_balance(asset_class, cash_after)
        order = await self.store.update_order_fill_state(order, size, fill_price, "filled")
        position_id = None if position is None else position.id
        fill = await self.store.create_fill(
            order_id=order.id,
            position_id=position_id,
            symbol=normalized_symbol,
            asset_class=asset_class,
            side=side,
            fill_size=size,
            fill_price=fill_price,
            commission=commission,
            realized_pnl=realized_pnl,
            cash_after=cash_after,
        )
        return PaperExecutionResult(order=order, fill=fill, position=position, account=account)

    async def _apply_buy_position(
        self,
        position: PaperPositionRow | None,
        symbol: str,
        asset_class: str,
        size: float,
        fill_price: float,
        strategy_id: str | None,
    ) -> PaperPositionRow:
        """Create or average into a long paper position."""

        if position is None:
            return await self.store.create_position(
                symbol=symbol,
                asset_class=asset_class,
                side="long",
                size=size,
                average_entry_price=fill_price,
                strategy_id=strategy_id,
            )

        existing_size = float(position.size)
        existing_average = float(position.average_entry_price)
        new_size = existing_size + size
        new_average = ((existing_size * existing_average) + (size * fill_price)) / new_size
        return await self.store.update_position_size(position, new_size, new_average)

    async def _apply_sell_position(
        self,
        position: PaperPositionRow,
        size: float,
        realized_pnl: float,
    ) -> PaperPositionRow | None:
        """Reduce or close a long paper position."""

        existing_size = float(position.size)
        if size > existing_size:
            raise ValueError("cannot sell more than the open durable paper position")
        remaining_size = existing_size - size
        if remaining_size == 0.0:
            return await self.store.close_position(position, realized_pnl)
        return await self.store.update_position_size(
            position,
            remaining_size,
            float(position.average_entry_price),
        )

    def _commission(self, asset_class: str, gross: float) -> float:
        """Return paper commission for the asset class."""

        rate = CRYPTO_COMMISSION_RATE if asset_class == "crypto" else STOCK_COMMISSION_RATE
        return gross * rate

    def _validate_fill_request(self, side: str, size: float, fill_price: float) -> None:
        """Validate a paper fill request before any durable write is made."""

        if side not in {"buy", "sell"}:
            raise ValueError("paper side must be 'buy' or 'sell'")
        if size <= 0.0:
            raise ValueError("paper fill size must be positive")
        if fill_price <= 0.0:
            raise ValueError("paper fill price must be positive")
