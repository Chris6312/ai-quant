"""Phase S4 stock universe composition tests."""

from __future__ import annotations

from app.stock.universe import (
    StockUniverseSource,
    StockUniverseTier,
    build_stock_universe,
)


def test_same_symbol_from_multiple_tiers_merges_metadata() -> None:
    """Overlapping universe inputs should keep all tier and source provenance."""

    universe = build_stock_universe(
        sp500=[" aapl "],
        nasdaq100=["AAPL"],
        high_volume=["AAPL"],
        manual=["aapl"],
    )

    candidate = universe[0]

    assert candidate.symbol == "AAPL"
    assert candidate.tiers == (
        StockUniverseTier.SP500,
        StockUniverseTier.NASDAQ100,
        StockUniverseTier.HIGH_VOLUME,
        StockUniverseTier.MANUAL,
    )
    assert candidate.sources == (
        StockUniverseSource.INDEX,
        StockUniverseSource.LIQUIDITY,
        StockUniverseSource.MANUAL,
    )
    assert candidate.raw_symbols == (" aapl ", "AAPL", "aapl")


def test_duplicate_tiers_and_sources_are_not_repeated() -> None:
    """Repeated inputs from the same source should not duplicate metadata."""

    universe = build_stock_universe(
        sp500=["MSFT", "msft"],
        nasdaq100=["MSFT"],
    )

    candidate = universe[0]

    assert candidate.tiers == (
        StockUniverseTier.SP500,
        StockUniverseTier.NASDAQ100,
    )
    assert candidate.sources == (StockUniverseSource.INDEX,)


def test_universe_ordering_uses_highest_priority_tier_then_symbol() -> None:
    """Merged output should be stable after dedupe."""

    universe = build_stock_universe(
        nasdaq100=["MSFT"],
        high_volume=["TSLA"],
        manual=["AAPL"],
        event_driven=["NVDA"],
        sp500=["GOOGL"],
    )

    assert [candidate.symbol for candidate in universe] == [
        "GOOGL",
        "MSFT",
        "TSLA",
        "AAPL",
        "NVDA",
    ]
