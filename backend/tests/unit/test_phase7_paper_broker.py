"""Tests for the internal paper broker."""

from __future__ import annotations

import pytest

from app.brokers.paper import PaperBroker


@pytest.mark.asyncio
async def test_paper_broker_rejects_crypto_short_orders() -> None:
    """Crypto shorts are blocked regardless of balance."""

    broker = PaperBroker()
    order = await broker.submit_order("BTC/USD", "sell", 0.5, "market")
    assert order.status == "rejected"
    balance = await broker.get_account_balance()
    assert balance["crypto_balance"] == broker.starting_crypto_cash


@pytest.mark.asyncio
async def test_paper_broker_blocks_stock_short_when_balance_is_low() -> None:
    """Stock shorts should respect the paper stock balance gate."""

    broker = PaperBroker(starting_cash=2_000.0)
    order = await broker.submit_order("AAPL", "sell", 10.0, "market")
    assert order.status == "rejected"


@pytest.mark.asyncio
async def test_paper_broker_fills_market_orders_and_tracks_nav() -> None:
    """Market orders should fill and update NAV consistently."""

    broker = PaperBroker(starting_cash=100_000.0, starting_crypto_cash=50_000.0)
    broker.set_market_data("AAPL", last_price=100.0, last_volume=1_000_000.0)
    order = await broker.submit_order("AAPL", "buy", 10.0, "market")
    assert order.status == "filled"
    balance = await broker.get_account_balance()
    assert balance["equity"] > 0.0
    assert balance["realized_pnl"] <= 0.0


@pytest.mark.asyncio
async def test_paper_broker_partially_fills_large_orders() -> None:
    """Large orders should be partially filled over successive candles."""

    broker = PaperBroker(starting_cash=100_000.0)
    broker.set_market_data("AAPL", last_price=100.0, last_volume=1_000.0)
    order = await broker.submit_order("AAPL", "buy", 20.0, "market")
    assert order.status in {"partial", "filled"}


@pytest.mark.asyncio
async def test_paper_broker_halt_blocks_new_orders() -> None:
    """The kill switch should stop new order submission."""

    broker = PaperBroker()
    broker.halt()
    order = await broker.submit_order("AAPL", "buy", 1.0, "market")
    assert order.status == "rejected"
