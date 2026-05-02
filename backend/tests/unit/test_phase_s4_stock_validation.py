"""Phase S4 stock validation tests."""

from __future__ import annotations

from app.stock.universe import (
    StockUniverseCandidate,
    StockUniverseSource,
    StockUniverseTier,
)
from app.stock.validation import (
    StockEarningsRiskSnapshot,
    StockLiquiditySnapshot,
    StockScreeningThresholds,
    StockTradabilitySnapshot,
    screen_stock_candidate,
    validate_earnings_danger_placeholder,
)


def _candidate(symbol: str = "AAPL") -> StockUniverseCandidate:
    return StockUniverseCandidate(
        symbol=symbol,
        provider_symbol=symbol,
        tiers=(StockUniverseTier.SP500,),
        sources=(StockUniverseSource.INDEX,),
        raw_symbols=(symbol,),
        is_supported=True,
    )


def _liquidity_snapshot(
    *,
    symbol: str = "AAPL",
    price: float = 100.0,
    average_daily_volume: float = 2_000_000.0,
    dollar_volume: float = 200_000_000.0,
    bid: float | None = 99.95,
    ask: float | None = 100.05,
    is_halted: bool = False,
    is_excluded: bool = False,
) -> StockLiquiditySnapshot:
    return StockLiquiditySnapshot(
        symbol=symbol,
        price=price,
        average_daily_volume=average_daily_volume,
        dollar_volume=dollar_volume,
        bid=bid,
        ask=ask,
        is_halted=is_halted,
        is_excluded=is_excluded,
    )


def _tradability_snapshot(
    *,
    symbol: str = "AAPL",
    is_tradable: bool = True,
    reason: str | None = None,
) -> StockTradabilitySnapshot:
    return StockTradabilitySnapshot(
        symbol=symbol,
        is_tradable=is_tradable,
        reason=reason,
    )


def _earnings_snapshot(
    *,
    symbol: str = "AAPL",
    is_in_danger_window: bool = False,
    reason: str | None = None,
) -> StockEarningsRiskSnapshot:
    return StockEarningsRiskSnapshot(
        symbol=symbol,
        is_in_danger_window=is_in_danger_window,
        reason=reason,
    )


def _screen(
    *,
    liquidity_snapshot: StockLiquiditySnapshot | None = None,
    tradability_snapshot: StockTradabilitySnapshot | None = None,
    earnings_risk_snapshot: StockEarningsRiskSnapshot | None = None,
    sector: str | None = "Technology",
) -> tuple[str, ...]:
    result = screen_stock_candidate(
        candidate=_candidate(),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=liquidity_snapshot or _liquidity_snapshot(),
        tradability_snapshot=tradability_snapshot or _tradability_snapshot(),
        earnings_risk_snapshot=earnings_risk_snapshot or _earnings_snapshot(),
        sector=sector,
    )
    return tuple(failure.code for failure in result.failures)


def test_price_below_threshold_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(price=4.99)) == (
        "price_below_minimum",
    )


def test_dollar_volume_below_threshold_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(dollar_volume=1_000_000.0)) == (
        "dollar_volume_below_minimum",
    )


def test_liquidity_snapshot_fail() -> None:
    assert _screen(
        liquidity_snapshot=_liquidity_snapshot(average_daily_volume=100_000.0),
    ) == ("average_daily_volume_below_minimum",)


def test_spread_too_wide_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(bid=99.0, ask=101.0)) == (
        "spread_above_maximum",
    )


def test_inverted_spread_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(bid=101.0, ask=99.0)) == (
        "spread_inverted",
    )


def test_nan_price_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(price=float("nan"))) == (
        "price_non_finite",
    )


def test_infinite_dollar_volume_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(dollar_volume=float("inf"))) == (
        "dollar_volume_non_finite",
    )


def test_nan_spread_input_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(bid=float("nan"))) == (
        "spread_input_non_finite",
    )


def test_halted_or_excluded_fails() -> None:
    assert _screen(liquidity_snapshot=_liquidity_snapshot(is_halted=True)) == (
        "symbol_halted",
    )
    assert _screen(liquidity_snapshot=_liquidity_snapshot(is_excluded=True)) == (
        "symbol_excluded",
    )


def test_tradability_snapshot_fail() -> None:
    assert _screen(
        tradability_snapshot=_tradability_snapshot(
            is_tradable=False,
            reason="not supported by broker",
        ),
    ) == ("symbol_not_tradable",)


def test_missing_sector_classification_fails() -> None:
    assert _screen(sector=None) == ("sector_classification_missing",)
    assert _screen(sector=" ") == ("sector_classification_missing",)


def test_earnings_risk_placeholder_returns_deterministic_result() -> None:
    result = validate_earnings_danger_placeholder(
        symbol="AAPL",
        snapshot=_earnings_snapshot(
            is_in_danger_window=True,
            reason="earnings within configured placeholder window",
        ),
        thresholds=StockScreeningThresholds(),
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == ["earnings_danger_window"]
    assert result.failures[0].reason == "earnings within configured placeholder window"


def test_missing_liquidity_snapshot_fails() -> None:
    result = screen_stock_candidate(
        candidate=_candidate(),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=None,
        tradability_snapshot=_tradability_snapshot(),
        earnings_risk_snapshot=_earnings_snapshot(),
        sector="Technology",
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == [
        "price_missing",
        "dollar_volume_missing",
        "liquidity_snapshot_missing",
        "spread_snapshot_missing",
        "halt_exclusion_snapshot_missing",
    ]


def test_missing_tradability_snapshot_fails() -> None:
    result = screen_stock_candidate(
        candidate=_candidate(),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=_liquidity_snapshot(),
        tradability_snapshot=None,
        earnings_risk_snapshot=_earnings_snapshot(),
        sector="Technology",
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == ["tradability_snapshot_missing"]


def test_missing_inputs_are_included_in_aggregate_result() -> None:
    result = screen_stock_candidate(
        candidate=_candidate(),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=None,
        tradability_snapshot=None,
        earnings_risk_snapshot=None,
        sector=None,
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == [
        "price_missing",
        "dollar_volume_missing",
        "liquidity_snapshot_missing",
        "spread_snapshot_missing",
        "halt_exclusion_snapshot_missing",
        "tradability_snapshot_missing",
        "earnings_risk_snapshot_missing",
        "sector_classification_missing",
    ]


def test_snapshot_symbol_mismatch_fails() -> None:
    result = screen_stock_candidate(
        candidate=_candidate("AAPL"),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=_liquidity_snapshot(symbol="MSFT"),
        tradability_snapshot=_tradability_snapshot(),
        earnings_risk_snapshot=_earnings_snapshot(),
        sector="Technology",
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == ["snapshot_symbol_mismatch"]
    assert result.failures[0].reason == (
        "Snapshot symbol mismatch: expected AAPL, got MSFT"
    )


def test_symbol_mismatch_is_included_in_aggregate_result() -> None:
    result = screen_stock_candidate(
        candidate=_candidate("AAPL"),
        thresholds=StockScreeningThresholds(),
        liquidity_snapshot=_liquidity_snapshot(
            symbol="MSFT",
            price=float("nan"),
            bid=101.0,
            ask=99.0,
        ),
        tradability_snapshot=_tradability_snapshot(symbol="TSLA"),
        earnings_risk_snapshot=_earnings_snapshot(symbol="NVDA"),
        sector="Technology",
    )

    assert result.passed is False
    assert [failure.code for failure in result.failures] == [
        "snapshot_symbol_mismatch",
        "snapshot_symbol_mismatch",
        "snapshot_symbol_mismatch",
        "price_non_finite",
        "spread_inverted",
    ]


def test_screen_stock_candidate_aggregates_failures() -> None:
    result_codes = _screen(
        liquidity_snapshot=_liquidity_snapshot(
            price=1.0,
            average_daily_volume=10_000.0,
            dollar_volume=20_000.0,
            bid=99.0,
            ask=101.0,
            is_halted=True,
        ),
        tradability_snapshot=_tradability_snapshot(is_tradable=False),
        earnings_risk_snapshot=_earnings_snapshot(is_in_danger_window=True),
        sector=None,
    )

    assert result_codes == (
        "price_below_minimum",
        "dollar_volume_below_minimum",
        "average_daily_volume_below_minimum",
        "spread_above_maximum",
        "symbol_halted",
        "symbol_not_tradable",
        "earnings_danger_window",
        "sector_classification_missing",
    )
