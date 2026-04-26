"""Repository for durable paper ledger persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import PaperAccountRow, PaperFillRow, PaperOrderRow, PaperPositionRow
from app.repositories.base import BaseRepository

OPEN_POSITION_STATUS = "open"
CLOSED_POSITION_STATUS = "closed"
PAPER_ORDER_SOURCE = "paper"


class PaperLedgerRepository(BaseRepository):
    """Persist and restore paper account, position, order, and fill state."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_account(self, asset_class: str) -> PaperAccountRow | None:
        """Return the durable paper account row for an asset class."""

        statement = select(PaperAccountRow).where(PaperAccountRow.asset_class == asset_class)
        result = await self.session.scalars(statement)
        return result.one_or_none()

    async def get_or_create_account(
        self,
        asset_class: str,
        default_cash_balance: float,
    ) -> PaperAccountRow:
        """Return an existing account or create a durable default account."""

        existing = await self.get_account(asset_class)
        if existing is not None:
            return existing

        now = datetime.now(tz=UTC)
        account = PaperAccountRow(
            id=str(uuid4()),
            asset_class=asset_class,
            cash_balance=default_cash_balance,
            default_cash_balance=default_cash_balance,
            realized_pnl=0.0,
            reset_count=0,
            last_reset_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def list_accounts(self) -> list[PaperAccountRow]:
        """Return all durable paper accounts."""

        statement = select(PaperAccountRow).order_by(PaperAccountRow.asset_class)
        result = await self.session.scalars(statement)
        return list(result)

    async def set_account_balance(
        self,
        asset_class: str,
        cash_balance: float,
        default_cash_balance: float | None = None,
    ) -> PaperAccountRow:
        """Set durable account cash and optionally update the reset default."""

        account = await self.get_or_create_account(asset_class, cash_balance)
        account.cash_balance = cash_balance
        if default_cash_balance is not None:
            account.default_cash_balance = default_cash_balance
        account.updated_at = datetime.now(tz=UTC)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def reset_account(self, asset_class: str) -> PaperAccountRow:
        """Reset one account to its configured default balance."""

        account = await self.get_account(asset_class)
        if account is None:
            raise ValueError(f"paper account does not exist for asset_class={asset_class!r}")
        now = datetime.now(tz=UTC)
        account.cash_balance = account.default_cash_balance
        account.realized_pnl = 0.0
        account.reset_count += 1
        account.last_reset_at = now
        account.updated_at = now
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def list_open_positions(self, asset_class: str | None = None) -> list[PaperPositionRow]:
        """Return open paper positions, optionally scoped by asset class."""

        conditions = [PaperPositionRow.status == OPEN_POSITION_STATUS]
        if asset_class is not None:
            conditions.append(PaperPositionRow.asset_class == asset_class)
        statement = (
            select(PaperPositionRow)
            .where(*conditions)
            .order_by(PaperPositionRow.asset_class, PaperPositionRow.symbol)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def get_open_position(self, symbol: str) -> PaperPositionRow | None:
        """Return the open durable position for a symbol, if one exists."""

        statement = select(PaperPositionRow).where(
            PaperPositionRow.symbol == symbol.upper(),
            PaperPositionRow.status == OPEN_POSITION_STATUS,
        )
        result = await self.session.scalars(statement)
        return result.one_or_none()

    async def create_position(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        size: float,
        average_entry_price: float,
        strategy_id: str | None = None,
    ) -> PaperPositionRow:
        """Create and persist an open paper position."""

        now = datetime.now(tz=UTC)
        position = PaperPositionRow(
            id=str(uuid4()),
            symbol=symbol.upper(),
            asset_class=asset_class,
            side=side,
            size=size,
            average_entry_price=average_entry_price,
            realized_pnl=0.0,
            status=OPEN_POSITION_STATUS,
            strategy_id=strategy_id,
            opened_at=now,
            updated_at=now,
            closed_at=None,
        )
        self.session.add(position)
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def update_position_size(
        self,
        position: PaperPositionRow,
        size: float,
        average_entry_price: float,
    ) -> PaperPositionRow:
        """Update an open position's size and average entry price."""

        position.size = size
        position.average_entry_price = average_entry_price
        position.updated_at = datetime.now(tz=UTC)
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def close_position(
        self,
        position: PaperPositionRow,
        realized_pnl: float,
    ) -> PaperPositionRow:
        """Mark a paper position closed and persist realized PnL."""

        now = datetime.now(tz=UTC)
        position.size = 0.0
        position.realized_pnl += realized_pnl
        position.status = CLOSED_POSITION_STATUS
        position.updated_at = now
        position.closed_at = now
        await self.session.commit()
        await self.session.refresh(position)
        return position

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
        """Persist a paper order before fills are applied."""

        now = datetime.now(tz=UTC)
        order = PaperOrderRow(
            id=str(uuid4()),
            symbol=symbol.upper(),
            asset_class=asset_class,
            side=side,
            order_type=order_type,
            requested_size=requested_size,
            limit_price=limit_price,
            status=status,
            filled_size=0.0,
            average_fill_price=None,
            remaining_size=requested_size,
            strategy_id=strategy_id,
            source=PAPER_ORDER_SOURCE,
            reject_reason=None,
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def update_order_fill_state(
        self,
        order: PaperOrderRow,
        filled_size: float,
        average_fill_price: float,
        status: str,
    ) -> PaperOrderRow:
        """Persist order fill state after execution."""

        now = datetime.now(tz=UTC)
        order.filled_size = filled_size
        order.average_fill_price = average_fill_price
        order.remaining_size = max(order.requested_size - filled_size, 0.0)
        order.status = status
        order.updated_at = now
        if status in {"filled", "cancelled", "rejected"}:
            order.closed_at = now
        await self.session.commit()
        await self.session.refresh(order)
        return order

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
        """Persist an immutable paper fill event."""

        fill = PaperFillRow(
            id=str(uuid4()),
            order_id=order_id,
            position_id=position_id,
            symbol=symbol.upper(),
            asset_class=asset_class,
            side=side,
            fill_size=fill_size,
            fill_price=fill_price,
            gross=fill_size * fill_price,
            commission=commission,
            realized_pnl=realized_pnl,
            cash_after=cash_after,
            source=PAPER_ORDER_SOURCE,
            filled_at=datetime.now(tz=UTC),
        )
        self.session.add(fill)
        await self.session.commit()
        await self.session.refresh(fill)
        return fill

    async def list_fills(self, symbol: str | None = None) -> list[PaperFillRow]:
        """Return paper fills for audit and restart verification."""

        conditions: list[ColumnElement[bool]] = []
        if symbol is not None:
            conditions.append(PaperFillRow.symbol == symbol.upper())
        statement = select(PaperFillRow).where(*conditions).order_by(PaperFillRow.filled_at.desc())
        result = await self.session.scalars(statement)
        return list(result)

    async def list_orders(self, symbol: str | None = None) -> list[PaperOrderRow]:
        """Return persisted paper orders for audit and UI display."""

        conditions: list[ColumnElement[bool]] = []
        if symbol is not None:
            conditions.append(PaperOrderRow.symbol == symbol.upper())
        statement = (
            select(PaperOrderRow)
            .where(*conditions)
            .order_by(PaperOrderRow.created_at.desc())
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def restore_snapshot(
        self,
    ) -> tuple[Sequence[PaperAccountRow], Sequence[PaperPositionRow]]:
        """Load durable account cash and open positions for runtime restart."""

        accounts = await self.list_accounts()
        positions = await self.list_open_positions()
        return accounts, positions
