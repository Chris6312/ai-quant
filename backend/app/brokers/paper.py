"""Internal paper broker implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from random import Random
from typing import TYPE_CHECKING, Final, cast
from uuid import uuid4

from app.brokers.base import BaseBroker, Order, OrderSide, OrderStatus, OrderType
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.models.domain import Position
from app.portfolio.sizer import PositionSizer
from app.repositories.positions import PositionRepository
from app.services.direction_gate import DirectionGate

if TYPE_CHECKING:
    from app.db.models import PositionRow


LIQUID_STOCK_SLIPPAGE: Final[float] = 0.0005
ILLIQUID_STOCK_SLIPPAGE: Final[float] = 0.0015
CRYPTO_MIDCAP_SLIPPAGE: Final[float] = 0.0010
CRYPTO_TAKER_COMMISSION: Final[float] = 0.0016
PARTIAL_FILL_THRESHOLD: Final[float] = 0.005


@dataclass(slots=True)
class PaperOrderFill:
    """Track the fill state of an order."""

    order: Order
    remaining_size: float


class PaperBroker(BaseBroker):
    """Simulate brokerage behavior with realistic fills and risk checks."""

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        starting_crypto_cash: float = 100_000.0,
        position_repository: PositionRepository | None = None,
        sizer: PositionSizer | None = None,
        rng_seed: int | None = 7,
        stock_commission_flat: float = 0.0,
        stock_commission_pct: float = 0.0,
        crypto_commission_pct: float = CRYPTO_TAKER_COMMISSION,
    ) -> None:
        self.starting_cash = starting_cash
        self.starting_crypto_cash = starting_crypto_cash
        self.paper_stock_balance = starting_cash
        self.paper_crypto_balance = starting_crypto_cash
        self.realized_pnl = 0.0
        self.position_repository = position_repository
        self.sizer = sizer or PositionSizer()
        self.rng = Random(rng_seed)
        self.stock_commission_flat = stock_commission_flat
        self.stock_commission_pct = stock_commission_pct
        self.crypto_commission_pct = crypto_commission_pct
        self.direction_gate = DirectionGate()
        self._orders: dict[str, PaperOrderFill] = {}
        self._positions: dict[str, Position] = {}
        self._last_prices: dict[str, float] = {}
        self._last_volumes: dict[str, float] = {}
        self._halted = False

    @property
    def halted(self) -> bool:
        """Return True when trading has been halted."""

        return self._halted

    def halt(self) -> None:
        """Stop accepting new orders."""

        self._halted = True

    def resume(self) -> None:
        """Allow new orders again."""

        self._halted = False

    def set_market_data(self, symbol: str, last_price: float, last_volume: float) -> None:
        """Seed the latest market price and volume for a symbol."""

        self._last_prices[symbol.upper()] = last_price
        self._last_volumes[symbol.upper()] = last_volume

    async def get_nav(self) -> float:
        """Return net asset value."""

        return (await self.get_account_balance())["equity"]

    async def submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> Order:
        """Submit a new simulated order."""

        if self._halted:
            return self._reject(symbol, side, size, order_type, limit_price, "halted")

        asset_class = self._asset_class(symbol)
        direction = "short" if side == "sell" else "long"
        if not self.direction_gate.passes(
            asset_class,
            direction,
            self._balance_for_asset(asset_class),
        ):
            return self._reject(symbol, side, size, order_type, limit_price, "direction gate")

        if size <= 0.0:
            return self._reject(
                symbol,
                side,
                size,
                order_type,
                limit_price,
                "size must be positive",
            )

        order = Order.create(
            symbol,
            cast(OrderSide, side),
            size,
            cast(OrderType, order_type),
            limit_price,
        )
        order = self._transition(order, "submitted")
        last_price = self._last_price(symbol)
        fill_price = self._simulated_fill_price(symbol, asset_class, order, last_price)
        if fill_price is None:
            self._orders[order.id] = PaperOrderFill(order=order, remaining_size=size)
            return self._transition(order, "submitted")

        return await self._fill_order(order, asset_class, fill_price, size)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""

        entry = self._orders.pop(order_id, None)
        if entry is None:
            return False
        cancelled = self._transition(entry.order, "cancelled")
        self._orders[order_id] = PaperOrderFill(order=cancelled, remaining_size=0.0)
        return True

    async def get_position(self, symbol: str) -> Position | None:
        """Return the current simulated position for a symbol."""

        return self._positions.get(symbol.upper())

    async def get_account_balance(self) -> dict[str, float]:
        """Return a balance snapshot including NAV and P&L."""

        unrealized_pnl = self._unrealized_pnl()
        equity = self.paper_stock_balance + self.paper_crypto_balance + self._portfolio_value()
        return {
            "cash": self.paper_stock_balance,
            "equity": equity,
            "stock_balance": self.paper_stock_balance,
            "crypto_balance": self.paper_crypto_balance,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized_pnl,
        }

    async def get_open_orders(self) -> list[Order]:
        """Return active and pending orders."""

        return [
            entry.order
            for entry in self._orders.values()
            if entry.order.status in {"pending", "submitted", "partial"}
        ]

    async def process_candle(
        self,
        symbol: str,
        last_price: float,
        volume: float,
    ) -> list[Order]:
        """Advance pending orders using a new market candle."""

        symbol = symbol.upper()
        self.set_market_data(symbol, last_price, volume)
        updated: list[Order] = []
        for fill in list(self._orders.values()):
            if fill.order.symbol != symbol:
                continue
            if fill.order.order_type == "limit":
                if not self._limit_crossed(fill.order, last_price):
                    continue
                fill_price = self._apply_slippage(symbol, self._asset_class(symbol), last_price)
            else:
                fill_price = self._apply_slippage(symbol, self._asset_class(symbol), last_price)
            fill_order = await self._fill_remaining(fill, fill_price, volume)
            updated.append(fill_order)
        return updated

    def _asset_class(self, symbol: str) -> str:
        """Infer asset class from the symbol format."""

        normalized = symbol.upper()
        if normalized in KRAKEN_UNIVERSE or "/" in normalized:
            return "crypto"
        return "stock"

    def _balance_for_asset(self, asset_class: str) -> float:
        """Return the balance used for direction gating."""

        return self.paper_crypto_balance if asset_class == "crypto" else self.paper_stock_balance

    def _last_price(self, symbol: str) -> float:
        """Return the latest price or a safe fallback."""

        return self._last_prices.get(symbol.upper(), 100.0)

    def _last_volume(self, symbol: str) -> float:
        """Return the latest volume or a safe fallback."""

        return self._last_volumes.get(symbol.upper(), 1_000_000.0)

    def _simulated_fill_price(
        self,
        symbol: str,
        asset_class: str,
        order: Order,
        last_price: float,
    ) -> float | None:
        """Return an initial fill price or None when the order should remain pending."""

        if order.order_type == "limit" and not self._limit_crossed(order, last_price):
            return None
        return self._apply_slippage(symbol, asset_class, last_price)

    def _limit_crossed(self, order: Order, last_price: float) -> bool:
        """Return True when the market has crossed the limit price."""

        if order.limit_price is None:
            return False
        if order.side == "buy":
            return last_price <= order.limit_price
        return last_price >= order.limit_price

    def _apply_slippage(self, symbol: str, asset_class: str, last_price: float) -> float:
        """Apply a random slippage adjustment."""

        sigma = self._slippage_sigma(symbol, asset_class)
        return max(0.01, last_price * (1.0 + self.rng.gauss(0.0, sigma)))

    def _slippage_sigma(self, symbol: str, asset_class: str) -> float:
        """Return the slippage sigma for the asset."""

        if asset_class == "crypto":
            return CRYPTO_MIDCAP_SLIPPAGE
        volume = self._last_volume(symbol)
        if volume >= 1_000_000.0:
            return LIQUID_STOCK_SLIPPAGE
        return ILLIQUID_STOCK_SLIPPAGE

    async def _fill_order(
        self,
        order: Order,
        asset_class: str,
        fill_price: float,
        fill_size: float,
    ) -> Order:
        """Fill an order immediately."""

        fill_size = min(fill_size, order.size)
        commission = self._commission(asset_class, fill_size, fill_price)
        realized_delta = self._apply_position(asset_class, order, fill_price, fill_size)
        order = self._finalize_order(order, fill_size, fill_price)
        self._apply_cash_flow(asset_class, order.side, fill_price, fill_size, commission)
        self.realized_pnl += realized_delta - commission
        await self._persist_position(order, asset_class, fill_price, fill_size)
        return order

    async def _fill_remaining(
        self,
        fill: PaperOrderFill,
        fill_price: float,
        volume: float,
    ) -> Order:
        """Fill some or all of a pending order based on candle volume."""

        asset_class = self._asset_class(fill.order.symbol)
        max_fill = max(fill.remaining_size, volume * PARTIAL_FILL_THRESHOLD)
        fill_size = min(fill.remaining_size, max_fill)
        if fill_size <= 0.0:
            return fill.order
        commission = self._commission(asset_class, fill_size, fill_price)
        realized_delta = self._apply_position(asset_class, fill.order, fill_price, fill_size)
        updated_order = self._finalize_order(
            fill.order,
            fill_size,
            fill_price,
            partial=fill_size < fill.remaining_size,
        )
        self._apply_cash_flow(asset_class, updated_order.side, fill_price, fill_size, commission)
        self.realized_pnl += realized_delta - commission
        fill.remaining_size -= fill_size
        if fill.remaining_size <= 0.0:
            self._orders.pop(fill.order.id, None)
        else:
            self._orders[fill.order.id] = PaperOrderFill(
                order=updated_order,
                remaining_size=fill.remaining_size,
            )
        await self._persist_position(updated_order, asset_class, fill_price, fill_size)
        return updated_order

    def _commission(self, asset_class: str, size: float, fill_price: float) -> float:
        """Return the commission for a fill."""

        if asset_class == "crypto":
            return size * fill_price * self.crypto_commission_pct
        return self.stock_commission_flat + (size * fill_price * self.stock_commission_pct)

    def _apply_cash_flow(
        self,
        asset_class: str,
        side: str,
        fill_price: float,
        fill_size: float,
        commission: float,
    ) -> None:
        """Update cash balances after a fill."""

        gross = fill_price * fill_size
        if asset_class == "crypto":
            if side == "buy":
                self.paper_crypto_balance -= gross + commission
            else:
                self.paper_crypto_balance += gross - commission
        else:
            if side == "buy":
                self.paper_stock_balance -= gross + commission
            else:
                self.paper_stock_balance += gross - commission
        self.realized_pnl -= commission

    def _apply_position(
        self,
        asset_class: str,
        order: Order,
        fill_price: float,
        fill_size: float,
    ) -> float:
        """Update simulated positions after a fill and return realized P&L."""

        existing = self._positions.get(order.symbol)
        if order.side == "buy":
            if existing is None:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    asset_class=asset_class,
                    side="long",
                    entry_price=fill_price,
                    size=fill_size,
                    sl_price=None,
                    tp_price=None,
                    strategy_id=None,
                    ml_confidence=None,
                    research_score=None,
                    status="open",
                )
                return 0.0
            if existing.side == "short":
                closed_size = min(existing.size, fill_size)
                realized = (existing.entry_price - fill_price) * closed_size
                remaining = existing.size - closed_size
                if remaining <= 0.0:
                    self._positions.pop(order.symbol, None)
                else:
                    self._positions[order.symbol] = Position(
                        symbol=existing.symbol,
                        asset_class=existing.asset_class,
                        side="short",
                        entry_price=existing.entry_price,
                        size=remaining,
                        sl_price=existing.sl_price,
                        tp_price=existing.tp_price,
                        strategy_id=existing.strategy_id,
                        ml_confidence=existing.ml_confidence,
                        research_score=existing.research_score,
                        status=existing.status,
                    )
                return realized
            self._positions[order.symbol] = Position(
                symbol=existing.symbol,
                asset_class=existing.asset_class,
                side=existing.side,
                entry_price=(existing.entry_price * existing.size + fill_price * fill_size)
                / (existing.size + fill_size),
                size=existing.size + fill_size,
                sl_price=existing.sl_price,
                tp_price=existing.tp_price,
                strategy_id=existing.strategy_id,
                ml_confidence=existing.ml_confidence,
                research_score=existing.research_score,
                status=existing.status,
            )
            return 0.0
        if existing is None:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                asset_class=asset_class,
                side="short",
                entry_price=fill_price,
                size=fill_size,
                sl_price=None,
                tp_price=None,
                strategy_id=None,
                ml_confidence=None,
                research_score=None,
                status="open",
            )
            return 0.0
        if existing.side == "long":
            closed_size = min(existing.size, fill_size)
            realized = (fill_price - existing.entry_price) * closed_size
            remaining = existing.size - closed_size
            if remaining <= 0.0:
                self._positions.pop(order.symbol, None)
            else:
                self._positions[order.symbol] = Position(
                    symbol=existing.symbol,
                    asset_class=existing.asset_class,
                    side="long",
                    entry_price=existing.entry_price,
                    size=remaining,
                    sl_price=existing.sl_price,
                    tp_price=existing.tp_price,
                    strategy_id=existing.strategy_id,
                    ml_confidence=existing.ml_confidence,
                    research_score=existing.research_score,
                    status=existing.status,
                )
            return realized
        self._positions[order.symbol] = Position(
            symbol=existing.symbol,
            asset_class=existing.asset_class,
            side="short",
            entry_price=(existing.entry_price * existing.size + fill_price * fill_size)
            / (existing.size + fill_size),
            size=existing.size + fill_size,
            sl_price=existing.sl_price,
            tp_price=existing.tp_price,
            strategy_id=existing.strategy_id,
            ml_confidence=existing.ml_confidence,
            research_score=existing.research_score,
            status=existing.status,
        )
        return 0.0

    def _finalize_order(
        self,
        order: Order,
        fill_size: float,
        fill_price: float,
        partial: bool = False,
    ) -> Order:
        """Return a new order state after a fill."""

        status: OrderStatus = "partial" if partial else "filled"
        return Order(
            id=order.id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            order_type=order.order_type,
            limit_price=order.limit_price,
            status=status,
            filled_size=fill_size,
            average_fill_price=fill_price,
            created_at=order.created_at,
            updated_at=datetime.now(tz=UTC),
        )

    def _transition(self, order: Order, status: OrderStatus) -> Order:
        """Return a new order with an updated status."""

        return Order(
            id=order.id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            order_type=order.order_type,
            limit_price=order.limit_price,
            status=status,
            filled_size=order.filled_size,
            average_fill_price=order.average_fill_price,
            created_at=order.created_at,
            updated_at=datetime.now(tz=UTC),
        )

    def _reject(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None,
        reason: str,
    ) -> Order:
        """Return a rejected order."""

        order = Order.create(
            symbol,
            cast(OrderSide, side),
            size,
            cast(OrderType, order_type),
            limit_price,
        )
        return self._transition(order, "rejected")

    async def _persist_position(
        self,
        order: Order,
        asset_class: str,
        fill_price: float,
        fill_size: float,
    ) -> None:
        """Persist the resulting position when a repository is provided."""

        if self.position_repository is None or order.side != "buy":
            return
        position = self._positions[order.symbol]
        row = self._to_row(position)
        await self.position_repository.upsert_position(row)

    def _to_row(self, position: Position) -> PositionRow:
        """Convert a domain position to a persistence row."""

        from app.db.models import PositionRow

        return PositionRow(
            id=str(uuid4()),
            symbol=position.symbol,
            asset_class=position.asset_class,
            side=position.side,
            entry_price=position.entry_price,
            size=position.size,
            sl_price=position.sl_price,
            tp_price=position.tp_price,
            strategy_id=position.strategy_id,
            ml_confidence=position.ml_confidence,
            research_score=position.research_score,
            status=position.status,
        )

    def _unrealized_pnl(self) -> float:
        """Return unrealized P&L across all open positions."""

        total = 0.0
        for position in self._positions.values():
            last_price = self._last_prices.get(position.symbol, position.entry_price)
            if position.side == "long":
                total += (last_price - position.entry_price) * position.size
            else:
                total += (position.entry_price - last_price) * position.size
        return total

    def _portfolio_value(self) -> float:
        """Return the market value of open positions."""

        total = 0.0
        for position in self._positions.values():
            last_price = self._last_prices.get(position.symbol, position.entry_price)
            if position.side == "long":
                total += last_price * position.size
            else:
                total -= last_price * position.size
        return total
