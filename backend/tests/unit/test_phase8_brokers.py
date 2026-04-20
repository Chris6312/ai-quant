"""Tests for Phase 8 live broker routing and halt controls."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.brokers.base import BaseBroker, Order
from app.brokers.router import BrokerRouter
from app.models.domain import Position


@dataclass
class _FakeBroker(BaseBroker):
    halted: bool = False
    submitted: list[tuple[str, str, float, str, float | None]] = None

    def __post_init__(self) -> None:
        self.submitted = []

    async def submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> Order:
        self.submitted.append((symbol, side, size, order_type, limit_price))
        return Order.create(symbol, side, size, order_type, limit_price)

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_position(self, symbol: str) -> Position | None:
        return None

    async def get_account_balance(self) -> dict[str, float]:
        return {"cash": 0.0, "equity": 0.0}

    async def get_open_orders(self) -> list[Order]:
        return []

    def halt(self) -> None:
        self.halted = True


@pytest.mark.asyncio
async def test_broker_router_routes_crypto_and_stock_symbols() -> None:
    """Crypto should route to Kraken and stocks to Tradier."""

    kraken = _FakeBroker()
    tradier = _FakeBroker()
    router = BrokerRouter(kraken=kraken, tradier=tradier)

    crypto_order = await router.submit_order("BTC/USD", "buy", 1.0, "market")
    stock_order = await router.submit_order("AAPL", "buy", 1.0, "market")

    assert crypto_order.symbol == "BTC/USD"
    assert stock_order.symbol == "AAPL"
    assert kraken.submitted[0][0] == "BTC/USD"
    assert tradier.submitted[0][0] == "AAPL"


@pytest.mark.asyncio
async def test_broker_router_halts_both_brokers() -> None:
    """The router should halt both brokers."""

    kraken = _FakeBroker()
    tradier = _FakeBroker()
    router = BrokerRouter(kraken=kraken, tradier=tradier)

    result = await router.halt_all()

    assert result == {"kraken": True, "tradier": True}
    assert kraken.halted is True
    assert tradier.halted is True
