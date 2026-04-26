"""Phase 9 pre-trade sentiment enforcement tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.brokers.base import BaseBroker, Order
from app.brokers.router import BrokerRouter
from app.models.domain import Position
from app.risk.pre_trade import enforce_sentiment_pre_trade


@dataclass(slots=True)
class _FakeBroker(BaseBroker):
    halted: bool = False
    submitted: list[tuple[str, str, float, str, float | None]] = field(
        default_factory=list
    )

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


def test_pre_trade_blocks_blocked_crypto_sentiment_gate() -> None:
    """A blocked sentiment gate should stop crypto execution."""

    decision = enforce_sentiment_pre_trade(
        symbol="BTC/USD",
        asset_class="crypto",
        side="buy",
        requested_size=2.0,
        sentiment_gate={
            "state": "blocked",
            "allowed": False,
            "position_multiplier": 0.0,
            "final_confidence": 0.0,
        },
    )

    assert decision.allowed is False
    assert decision.state == "blocked"
    assert decision.adjusted_size == 0.0
    assert decision.position_multiplier == 0.0
    assert decision.final_confidence == 0.0


def test_pre_trade_scales_crypto_buy_by_sentiment_multiplier() -> None:
    """Execution should consume the position multiplier from sentiment risk."""

    decision = enforce_sentiment_pre_trade(
        symbol="SOL/USD",
        asset_class="crypto",
        side="buy",
        requested_size=4.0,
        sentiment_gate={
            "state": "downgraded",
            "allowed": True,
            "position_multiplier": 0.75,
            "final_confidence": 0.648,
        },
    )

    assert decision.allowed is True
    assert decision.state == "scaled"
    assert decision.adjusted_size == 3.0
    assert decision.position_multiplier == 0.75
    assert decision.final_confidence == 0.648


def test_pre_trade_leaves_stocks_outside_crypto_sentiment_scope() -> None:
    """BTC/ETH sentiment enforcement should not affect stock order sizing."""

    decision = enforce_sentiment_pre_trade(
        symbol="AAPL",
        asset_class="stock",
        side="buy",
        requested_size=10.0,
        sentiment_gate={
            "state": "blocked",
            "allowed": False,
            "position_multiplier": 0.0,
        },
    )

    assert decision.allowed is True
    assert decision.state == "unscoped"
    assert decision.adjusted_size == 10.0
    assert decision.position_multiplier == 1.0


@pytest.mark.asyncio
async def test_broker_router_blocks_crypto_order_when_sentiment_blocks() -> None:
    """The broker router should be the execution guardrail for blocked signals."""

    kraken = _FakeBroker()
    tradier = _FakeBroker()
    router = BrokerRouter(kraken=kraken, tradier=tradier)

    with pytest.raises(ValueError, match="Sentiment gate blocked"):
        await router.submit_order(
            "BTC/USD",
            "buy",
            2.0,
            "market",
            sentiment_gate={
                "state": "blocked",
                "allowed": False,
                "position_multiplier": 0.0,
            },
        )

    assert kraken.submitted == []


@pytest.mark.asyncio
async def test_broker_router_scales_crypto_order_before_submission() -> None:
    """The broker router should submit the sentiment-adjusted crypto size."""

    kraken = _FakeBroker()
    tradier = _FakeBroker()
    router = BrokerRouter(kraken=kraken, tradier=tradier)

    order = await router.submit_order(
        "ETH/USD",
        "buy",
        4.0,
        "market",
        sentiment_gate={
            "state": "downgraded",
            "allowed": True,
            "position_multiplier": 0.5,
            "final_confidence": 0.58,
        },
    )

    assert order.symbol == "ETH/USD"
    assert order.size == 2.0
    assert kraken.submitted == [("ETH/USD", "buy", 2.0, "market", None)]


@pytest.mark.asyncio
async def test_broker_router_does_not_apply_crypto_gate_to_stocks() -> None:
    """Stock orders remain untouched by the crypto macro sentiment payload."""

    kraken = _FakeBroker()
    tradier = _FakeBroker()
    router = BrokerRouter(kraken=kraken, tradier=tradier)

    order = await router.submit_order(
        "AAPL",
        "buy",
        10.0,
        "market",
        sentiment_gate={
            "state": "blocked",
            "allowed": False,
            "position_multiplier": 0.0,
        },
    )

    assert order.symbol == "AAPL"
    assert order.size == 10.0
    assert tradier.submitted == [("AAPL", "buy", 10.0, "market", None)]
