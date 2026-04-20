"""Route symbols to the correct live broker."""

from __future__ import annotations

from dataclasses import dataclass

from app.brokers.base import BaseBroker, Order
from app.brokers.kraken import KrakenBroker
from app.brokers.tradier import TradierBroker
from app.candle.kraken_worker import KRAKEN_UNIVERSE


@dataclass(slots=True)
class BrokerRouter:
    """Map each symbol to the correct live broker."""

    kraken: KrakenBroker
    tradier: TradierBroker

    def route(self, symbol: str) -> BaseBroker:
        """Return the broker responsible for a symbol."""

        if self.is_crypto(symbol):
            return self.kraken
        return self.tradier

    def is_crypto(self, symbol: str) -> bool:
        """Return True when the symbol belongs to the crypto universe."""

        normalized = symbol.upper()
        return normalized in KRAKEN_UNIVERSE or "/" in normalized

    async def submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> Order:
        """Submit an order to the appropriate broker."""

        broker = self.route(symbol)
        return await broker.submit_order(symbol, side, size, order_type, limit_price)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order with the broker handling the symbol."""

        broker = self.route(symbol)
        return await broker.cancel_order(order_id)

    async def get_account_snapshot(self) -> dict[str, dict[str, float]]:
        """Return both live broker balance snapshots."""

        return {
            "kraken": await self.kraken.get_account_balance(),
            "tradier": await self.tradier.get_account_balance(),
        }

    async def get_open_orders(self) -> dict[str, list[Order]]:
        """Return open orders grouped by broker."""

        return {
            "kraken": await self.kraken.get_open_orders(),
            "tradier": await self.tradier.get_open_orders(),
        }

    async def get_open_positions(self) -> dict[str, list[object]]:
        """Return open positions grouped by broker."""

        return {
            "kraken": await self.kraken.get_open_positions(),
            "tradier": await self.tradier.get_open_positions(),
        }

    async def halt_all(self) -> dict[str, bool]:
        """Halt both brokers by refusing new submissions."""

        self.kraken.halt()  # type: ignore[no-untyped-call]
        self.tradier.halt()  # type: ignore[no-untyped-call]
        return {"kraken": True, "tradier": True}

    def kraken_balance_halt(self) -> None:
        """Mark Kraken as halted when the broker supports it."""

        if hasattr(self.kraken, "halt"):
            self.kraken.halt()  # type: ignore[no-untyped-call]

    def tradier_balance_halt(self) -> None:
        """Mark Tradier as halted when the broker supports it."""

        if hasattr(self.tradier, "halt"):
            self.tradier.halt()  # type: ignore[no-untyped-call]
