"""Pure stock universe screening helpers.

This module validates provided stock snapshots only. It does not fetch data,
score candidates, write to storage, start workers, or make trading decisions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.stock.universe import StockUniverseCandidate


@dataclass(slots=True, frozen=True)
class StockScreeningThresholds:
    """Rule thresholds for deterministic stock universe screening."""

    min_price: float = 5.0
    max_price: float | None = 500.0
    min_dollar_volume: float = 5_000_000.0
    min_average_daily_volume: float = 1_000_000.0
    max_spread_percent: float = 1.0
    require_sector_classification: bool = True
    block_earnings_danger_window: bool = True


@dataclass(slots=True, frozen=True)
class StockLiquiditySnapshot:
    """Provided liquidity facts for one stock candidate."""

    symbol: str
    price: float
    average_daily_volume: float
    dollar_volume: float
    bid: float | None
    ask: float | None
    is_halted: bool = False
    is_excluded: bool = False


@dataclass(slots=True, frozen=True)
class StockTradabilitySnapshot:
    """Provided tradability facts for one stock candidate."""

    symbol: str
    is_tradable: bool
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class StockEarningsRiskSnapshot:
    """Provided earnings-window facts for one stock candidate."""

    symbol: str
    is_in_danger_window: bool
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class StockScreeningFailure:
    """One deterministic stock screening failure."""

    code: str
    reason: str


@dataclass(slots=True, frozen=True)
class StockScreeningResult:
    """Pass/fail result for one stock screening step or aggregate."""

    symbol: str
    passed: bool
    failures: tuple[StockScreeningFailure, ...] = ()


def validate_price(
    *,
    symbol: str,
    price: float | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate that a stock price is inside configured bounds."""

    if price is None:
        return _fail(
            symbol=symbol,
            code="price_missing",
            reason="price is missing",
        )
    if not math.isfinite(price):
        return _fail(
            symbol=symbol,
            code="price_non_finite",
            reason="Non-finite price value",
        )
    if price < thresholds.min_price:
        return _fail(
            symbol=symbol,
            code="price_below_minimum",
            reason=f"price {price:.2f} is below minimum {thresholds.min_price:.2f}",
        )
    if thresholds.max_price is not None and price > thresholds.max_price:
        return _fail(
            symbol=symbol,
            code="price_above_maximum",
            reason=f"price {price:.2f} is above maximum {thresholds.max_price:.2f}",
        )
    return _pass(symbol)


def validate_dollar_volume(
    *,
    symbol: str,
    dollar_volume: float | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate minimum dollar volume from a provided snapshot."""

    if dollar_volume is None:
        return _fail(
            symbol=symbol,
            code="dollar_volume_missing",
            reason="dollar volume is missing",
        )
    if not math.isfinite(dollar_volume):
        return _fail(
            symbol=symbol,
            code="dollar_volume_non_finite",
            reason="Non-finite dollar volume value",
        )
    if dollar_volume < thresholds.min_dollar_volume:
        return _fail(
            symbol=symbol,
            code="dollar_volume_below_minimum",
            reason=(
                f"dollar volume {dollar_volume:.2f} is below minimum "
                f"{thresholds.min_dollar_volume:.2f}"
            ),
        )
    return _pass(symbol)


def validate_liquidity(
    *,
    symbol: str,
    snapshot: StockLiquiditySnapshot | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate provided average daily volume."""

    if snapshot is None:
        return _fail(
            symbol=symbol,
            code="liquidity_snapshot_missing",
            reason="liquidity snapshot is missing",
        )
    if not math.isfinite(snapshot.average_daily_volume):
        return _fail(
            symbol=snapshot.symbol,
            code="average_daily_volume_non_finite",
            reason="Non-finite liquidity value",
        )
    if snapshot.average_daily_volume < thresholds.min_average_daily_volume:
        return _fail(
            symbol=snapshot.symbol,
            code="average_daily_volume_below_minimum",
            reason=(
                f"average daily volume {snapshot.average_daily_volume:.2f} is below minimum "
                f"{thresholds.min_average_daily_volume:.2f}"
            ),
        )
    return _pass(snapshot.symbol)


def validate_spread(
    *,
    symbol: str,
    snapshot: StockLiquiditySnapshot | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate bid/ask spread percentage from a provided snapshot."""

    if snapshot is None:
        return _fail(
            symbol=symbol,
            code="spread_snapshot_missing",
            reason="liquidity snapshot is missing for spread validation",
        )
    if snapshot.bid is None or snapshot.ask is None:
        return _fail(
            symbol=snapshot.symbol,
            code="spread_quote_missing",
            reason="bid or ask is missing",
        )
    if not math.isfinite(snapshot.bid) or not math.isfinite(snapshot.ask):
        return _fail(
            symbol=snapshot.symbol,
            code="spread_input_non_finite",
            reason="Non-finite spread input",
        )
    if snapshot.ask < snapshot.bid:
        return _fail(
            symbol=snapshot.symbol,
            code="spread_inverted",
            reason="Inverted spread (ask < bid)",
        )
    midpoint = (snapshot.bid + snapshot.ask) / 2
    if not math.isfinite(midpoint):
        return _fail(
            symbol=snapshot.symbol,
            code="spread_midpoint_non_finite",
            reason="Non-finite spread input",
        )
    if midpoint <= 0:
        return _fail(
            symbol=snapshot.symbol,
            code="spread_midpoint_invalid",
            reason="bid/ask midpoint must be positive",
        )

    spread_percent = ((snapshot.ask - snapshot.bid) / midpoint) * 100
    if spread_percent > thresholds.max_spread_percent:
        return _fail(
            symbol=snapshot.symbol,
            code="spread_above_maximum",
            reason=(
                f"spread {spread_percent:.2f}% is above maximum "
                f"{thresholds.max_spread_percent:.2f}%"
            ),
        )
    return _pass(snapshot.symbol)


def validate_not_halted_or_excluded(
    *,
    symbol: str,
    snapshot: StockLiquiditySnapshot | None,
) -> StockScreeningResult:
    """Validate halt and explicit exclusion flags."""

    if snapshot is None:
        return _fail(
            symbol=symbol,
            code="halt_exclusion_snapshot_missing",
            reason="liquidity snapshot is missing for halt/exclusion validation",
        )
    if snapshot.is_halted:
        return _fail(
            symbol=snapshot.symbol,
            code="symbol_halted",
            reason="symbol is halted",
        )
    if snapshot.is_excluded:
        return _fail(
            symbol=snapshot.symbol,
            code="symbol_excluded",
            reason="symbol is excluded",
        )
    return _pass(snapshot.symbol)


def validate_tradability_snapshot(
    *,
    symbol: str,
    snapshot: StockTradabilitySnapshot | None,
) -> StockScreeningResult:
    """Validate a provided tradability snapshot."""

    if snapshot is None:
        return _fail(
            symbol=symbol,
            code="tradability_snapshot_missing",
            reason="tradability snapshot is missing",
        )
    if not snapshot.is_tradable:
        return _fail(
            symbol=snapshot.symbol,
            code="symbol_not_tradable",
            reason=snapshot.reason or "symbol is not tradable",
        )
    return _pass(snapshot.symbol)


def validate_earnings_danger_placeholder(
    *,
    symbol: str,
    snapshot: StockEarningsRiskSnapshot | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate a provided earnings danger-window placeholder."""

    if snapshot is None:
        return _fail(
            symbol=symbol,
            code="earnings_risk_snapshot_missing",
            reason="earnings risk snapshot is missing",
        )
    if thresholds.block_earnings_danger_window and snapshot.is_in_danger_window:
        return _fail(
            symbol=snapshot.symbol,
            code="earnings_danger_window",
            reason=snapshot.reason or "symbol is in earnings danger window",
        )
    return _pass(snapshot.symbol)


def validate_sector_classification(
    *,
    symbol: str,
    sector: str | None,
    thresholds: StockScreeningThresholds,
) -> StockScreeningResult:
    """Validate that sector classification is present when required."""

    if thresholds.require_sector_classification and not (sector and sector.strip()):
        return _fail(
            symbol=symbol,
            code="sector_classification_missing",
            reason="sector classification is missing",
        )
    return _pass(symbol)


def screen_stock_candidate(
    *,
    candidate: StockUniverseCandidate,
    thresholds: StockScreeningThresholds,
    liquidity_snapshot: StockLiquiditySnapshot | None,
    tradability_snapshot: StockTradabilitySnapshot | None,
    earnings_risk_snapshot: StockEarningsRiskSnapshot | None,
    sector: str | None,
) -> StockScreeningResult:
    """Aggregate deterministic screening checks for one stock candidate."""

    checks = (
        _validate_snapshot_symbol(
            expected_symbol=candidate.symbol,
            snapshot_symbol=liquidity_snapshot.symbol
            if liquidity_snapshot is not None
            else None,
        ),
        _validate_snapshot_symbol(
            expected_symbol=candidate.symbol,
            snapshot_symbol=tradability_snapshot.symbol
            if tradability_snapshot is not None
            else None,
        ),
        _validate_snapshot_symbol(
            expected_symbol=candidate.symbol,
            snapshot_symbol=earnings_risk_snapshot.symbol
            if earnings_risk_snapshot is not None
            else None,
        ),
        validate_price(
            symbol=candidate.symbol,
            price=liquidity_snapshot.price if liquidity_snapshot is not None else None,
            thresholds=thresholds,
        ),
        validate_dollar_volume(
            symbol=candidate.symbol,
            dollar_volume=liquidity_snapshot.dollar_volume
            if liquidity_snapshot is not None
            else None,
            thresholds=thresholds,
        ),
        validate_liquidity(
            symbol=candidate.symbol,
            snapshot=liquidity_snapshot,
            thresholds=thresholds,
        ),
        validate_spread(
            symbol=candidate.symbol,
            snapshot=liquidity_snapshot,
            thresholds=thresholds,
        ),
        validate_not_halted_or_excluded(
            symbol=candidate.symbol,
            snapshot=liquidity_snapshot,
        ),
        validate_tradability_snapshot(
            symbol=candidate.symbol,
            snapshot=tradability_snapshot,
        ),
        validate_earnings_danger_placeholder(
            symbol=candidate.symbol,
            snapshot=earnings_risk_snapshot,
            thresholds=thresholds,
        ),
        validate_sector_classification(
            symbol=candidate.symbol,
            sector=sector,
            thresholds=thresholds,
        ),
    )
    failures = tuple(failure for check in checks for failure in check.failures)
    return StockScreeningResult(
        symbol=candidate.symbol,
        passed=not failures,
        failures=failures,
    )


def _validate_snapshot_symbol(
    *,
    expected_symbol: str,
    snapshot_symbol: str | None,
) -> StockScreeningResult:
    if snapshot_symbol is not None and snapshot_symbol != expected_symbol:
        return _fail(
            symbol=expected_symbol,
            code="snapshot_symbol_mismatch",
            reason=(
                "Snapshot symbol mismatch: "
                f"expected {expected_symbol}, got {snapshot_symbol}"
            ),
        )
    return _pass(expected_symbol)


def _pass(symbol: str) -> StockScreeningResult:
    return StockScreeningResult(symbol=symbol, passed=True)


def _fail(*, symbol: str, code: str, reason: str) -> StockScreeningResult:
    return StockScreeningResult(
        symbol=symbol,
        passed=False,
        failures=(StockScreeningFailure(code=code, reason=reason),),
    )


__all__ = [
    "StockEarningsRiskSnapshot",
    "StockLiquiditySnapshot",
    "StockScreeningFailure",
    "StockScreeningResult",
    "StockScreeningThresholds",
    "StockTradabilitySnapshot",
    "screen_stock_candidate",
    "validate_dollar_volume",
    "validate_earnings_danger_placeholder",
    "validate_liquidity",
    "validate_not_halted_or_excluded",
    "validate_price",
    "validate_sector_classification",
    "validate_spread",
    "validate_tradability_snapshot",
]
