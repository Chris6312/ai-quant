"""BTC dominance macro weather tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.research.coingecko_client import classify_bitcoin_dominance


def test_btc_dominance_above_sixty_is_moderate_alt_headwind() -> None:
    """BTC.D above 60% should suppress altcoin promotion pressure."""

    reading = classify_bitcoin_dominance(
        value=60.6,
        as_of=datetime(2026, 4, 27, tzinfo=UTC),
    )

    assert reading.status == "available"
    assert reading.bias == "bearish"
    assert reading.effect == "headwind"
    assert reading.severity == "moderate"


def test_btc_dominance_low_level_is_alt_tailwind() -> None:
    """Low BTC.D should be treated as broad alt rotation pressure."""

    reading = classify_bitcoin_dominance(
        value=49.8,
        as_of=datetime(2026, 4, 27, tzinfo=UTC),
    )

    assert reading.bias == "bullish"
    assert reading.effect == "tailwind"
    assert reading.severity == "moderate"


def test_missing_btc_dominance_is_unknown_not_failure() -> None:
    """Bad provider payloads should not break macro weather."""

    reading = classify_bitcoin_dominance(value=None)

    assert reading.status == "unavailable"
    assert reading.bias == "unknown"
    assert reading.severity == "unknown"
