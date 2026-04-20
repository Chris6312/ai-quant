"""Tests for direction gating rules."""

from app.services.direction_gate import DirectionGate


def test_crypto_short_is_blocked() -> None:
    """Crypto shorts are never allowed."""

    gate = DirectionGate()
    assert gate.passes("crypto", "short", 100_000.0) is False


def test_stock_short_requires_balance() -> None:
    """Stocks can only short above the configured balance threshold."""

    gate = DirectionGate()
    assert gate.passes("stock", "short", 2_000.0) is False
    assert gate.passes("stock", "short", 3_000.0) is True
