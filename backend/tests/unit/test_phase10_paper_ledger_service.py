"""Phase 10 durable paper ledger repository/service checks."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.brokers.paper import PaperBroker
from app.db.models import PaperAccountRow, PaperFillRow, PaperOrderRow, PaperPositionRow
from app.paper.ledger_service import DEFAULT_PAPER_BALANCE, PaperLedgerService


class InMemoryPaperLedgerStore:
    """Small fake store proving the service uses persistence-facing methods."""

    def __init__(self) -> None:
        self.accounts: dict[str, PaperAccountRow] = {}
        self.positions: dict[str, PaperPositionRow] = {}
        self.orders: list[PaperOrderRow] = []
        self.fills: list[PaperFillRow] = []

    async def get_or_create_account(
        self,
        asset_class: str,
        default_cash_balance: float,
    ) -> PaperAccountRow:
        """Return or create an in-memory account shaped like the ORM row."""

        existing = self.accounts.get(asset_class)
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
        self.accounts[asset_class] = account
        return account

    async def set_account_balance(
        self,
        asset_class: str,
        cash_balance: float,
        default_cash_balance: float | None = None,
    ) -> PaperAccountRow:
        """Persist a fake account balance."""

        account = await self.get_or_create_account(asset_class, cash_balance)
        account.cash_balance = cash_balance
        if default_cash_balance is not None:
            account.default_cash_balance = default_cash_balance
        account.updated_at = datetime.now(tz=UTC)
        return account

    async def list_accounts(self) -> list[PaperAccountRow]:
        """Return fake durable accounts."""

        return sorted(self.accounts.values(), key=lambda row: row.asset_class)

    async def reset_account(self, asset_class: str) -> PaperAccountRow:
        """Reset a fake account to its default cash balance."""

        account = await self.get_or_create_account(asset_class, DEFAULT_PAPER_BALANCE)
        account.cash_balance = account.default_cash_balance
        account.realized_pnl = 0.0
        account.reset_count += 1
        account.last_reset_at = datetime.now(tz=UTC)
        account.updated_at = account.last_reset_at
        return account

    async def list_open_positions(self, asset_class: str | None = None) -> list[PaperPositionRow]:
        """Return open fake positions."""

        positions = [row for row in self.positions.values() if row.status == "open"]
        if asset_class is not None:
            positions = [row for row in positions if row.asset_class == asset_class]
        return positions

    async def get_open_position(self, symbol: str) -> PaperPositionRow | None:
        """Return an open fake position for a symbol."""

        position = self.positions.get(symbol.upper())
        if position is None or position.status != "open":
            return None
        return position

    async def create_position(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        size: float,
        average_entry_price: float,
        strategy_id: str | None = None,
    ) -> PaperPositionRow:
        """Create a fake position."""

        now = datetime.now(tz=UTC)
        position = PaperPositionRow(
            id=str(uuid4()),
            symbol=symbol.upper(),
            asset_class=asset_class,
            side=side,
            size=size,
            average_entry_price=average_entry_price,
            realized_pnl=0.0,
            status="open",
            strategy_id=strategy_id,
            opened_at=now,
            updated_at=now,
            closed_at=None,
        )
        self.positions[position.symbol] = position
        return position

    async def update_position_size(
        self,
        position: PaperPositionRow,
        size: float,
        average_entry_price: float,
    ) -> PaperPositionRow:
        """Update a fake position."""

        position.size = size
        position.average_entry_price = average_entry_price
        position.updated_at = datetime.now(tz=UTC)
        self.positions[position.symbol] = position
        return position

    async def close_position(
        self,
        position: PaperPositionRow,
        realized_pnl: float,
    ) -> PaperPositionRow:
        """Close a fake position."""

        position.size = 0.0
        position.realized_pnl += realized_pnl
        position.status = "closed"
        position.closed_at = datetime.now(tz=UTC)
        self.positions[position.symbol] = position
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
        """Create a fake order."""

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
            source="paper",
            reject_reason=None,
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        self.orders.append(order)
        return order

    async def update_order_fill_state(
        self,
        order: PaperOrderRow,
        filled_size: float,
        average_fill_price: float,
        status: str,
    ) -> PaperOrderRow:
        """Update fake order fill state."""

        order.filled_size = filled_size
        order.average_fill_price = average_fill_price
        order.remaining_size = max(order.requested_size - filled_size, 0.0)
        order.status = status
        order.updated_at = datetime.now(tz=UTC)
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
        """Create a fake immutable fill."""

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
            source="paper",
            filled_at=datetime.now(tz=UTC),
        )
        self.fills.append(fill)
        return fill

    async def list_orders(self, symbol: str | None = None) -> list[PaperOrderRow]:
        """Return fake durable orders."""

        if symbol is None:
            return list(self.orders)
        return [order for order in self.orders if order.symbol == symbol.upper()]

    async def list_fills(self, symbol: str | None = None) -> list[PaperFillRow]:
        """Return fake durable fills."""

        if symbol is None:
            return list(self.fills)
        return [fill for fill in self.fills if fill.symbol == symbol.upper()]


@pytest.mark.asyncio
async def test_restore_snapshot_bootstraps_durable_accounts() -> None:
    """Restart restore should create durable stock/crypto accounts if missing."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)

    snapshot = await service.restore_snapshot()

    assert snapshot.stock_cash == DEFAULT_PAPER_BALANCE
    assert snapshot.crypto_cash == DEFAULT_PAPER_BALANCE
    assert snapshot.open_positions == ()
    assert set(store.accounts) == {"stock", "crypto"}


@pytest.mark.asyncio
async def test_buy_fill_persists_order_fill_account_and_position() -> None:
    """A buy must write every durable ledger record needed after restart."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)

    result = await service.execute_market_fill(
        symbol="btc/usd",
        asset_class="crypto",
        side="buy",
        size=0.5,
        fill_price=50_000.0,
        strategy_id="phase10-test",
    )

    assert result.order.status == "filled"
    assert result.order.filled_size == 0.5
    assert result.position is not None
    assert result.fill.position_id == result.position.id
    assert result.account.cash_balance == pytest.approx(74_960.0)
    assert result.position.symbol == "BTC/USD"
    assert result.position.size == 0.5
    assert result.position.average_entry_price == 50_000.0
    assert len(store.orders) == 1
    assert len(store.fills) == 1


@pytest.mark.asyncio
async def test_sell_fill_reduces_position_and_records_realized_pnl() -> None:
    """A sell must reduce durable position state and persist fill PnL."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)
    await service.execute_market_fill("BTC/USD", "crypto", "buy", 1.0, 50_000.0)

    result = await service.execute_market_fill("BTC/USD", "crypto", "sell", 0.4, 55_000.0)

    assert result.position is not None
    assert result.position.status == "open"
    assert result.position.size == pytest.approx(0.6)
    assert result.fill.realized_pnl == pytest.approx(1_964.8)
    assert result.account.cash_balance == pytest.approx(71_884.8)


@pytest.mark.asyncio
async def test_sell_without_open_position_is_rejected_before_fill() -> None:
    """The service must not invent positions from candles or runtime memory."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)

    with pytest.raises(ValueError, match="cannot sell without an open durable"):
        await service.execute_market_fill("BTC/USD", "crypto", "sell", 1.0, 50_000.0)

    assert store.fills == []


@pytest.mark.asyncio
async def test_paper_broker_routes_fills_to_durable_ledger() -> None:
    """Paper broker execution must write orders, fills, cash, and positions durably."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)
    broker = PaperBroker(ledger_service=service, rng_seed=7)
    broker.set_market_data("BTC/USD", 50_000.0, 1_000_000.0)

    order = await broker.submit_order("BTC/USD", "buy", 0.25, "market")

    position = await broker.get_position("BTC/USD")
    balance = await broker.get_account_balance()
    account = store.accounts["crypto"]

    assert order.status == "filled"
    assert position is not None
    assert position.symbol == "BTC/USD"
    assert len(store.orders) == 1
    assert len(store.fills) == 1
    assert account.cash_balance == pytest.approx(balance["crypto_balance"])


@pytest.mark.asyncio
async def test_paper_broker_restores_durable_ledger_state() -> None:
    """A fresh broker should rebuild its paper mirror from persisted ledger state."""

    store = InMemoryPaperLedgerStore()
    service = PaperLedgerService(store)
    await service.execute_market_fill("ETH/USD", "crypto", "buy", 2.0, 2_500.0)

    broker = PaperBroker(ledger_service=service)
    await broker.restore_durable_state()

    position = await broker.get_position("ETH/USD")
    balance = await broker.get_account_balance()

    assert position is not None
    assert position.size == pytest.approx(2.0)
    assert position.entry_price == pytest.approx(2_500.0)
    assert balance["crypto_balance"] == pytest.approx(94_992.0)
