"""Portfolio-level risk controls for Phase 6."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.config.constants import (
    DAILY_LOSS_LIMIT_PCT,
    DEFAULT_MAX_CRYPTO_POSITIONS,
    DEFAULT_MAX_STOCK_POSITIONS,
    LIQUIDITY_POSITION_PCT,
    MAX_OPEN_POSITIONS,
    MAX_TOTAL_CAPITAL_AT_RISK_PCT,
    PEAK_DRAWDOWN_LIMIT_PCT,
    STOCK_SHORT_BALANCE_THRESHOLD,
    WEEKLY_DRAWDOWN_LIMIT_PCT,
)
from app.models.domain import Position


@dataclass(slots=True, frozen=True)
class RiskAssessment:
    """Represent the outcome of a risk check."""

    allowed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class RiskEngine:
    """Evaluate portfolio-level risk constraints before order submission."""

    def __init__(
        self,
        max_positions: int = MAX_OPEN_POSITIONS,
        max_stock_positions: int = DEFAULT_MAX_STOCK_POSITIONS,
        max_crypto_positions: int = DEFAULT_MAX_CRYPTO_POSITIONS,
        liquidity_position_pct: float = LIQUIDITY_POSITION_PCT,
        max_total_capital_at_risk_pct: float = MAX_TOTAL_CAPITAL_AT_RISK_PCT,
        daily_loss_limit_pct: float = DAILY_LOSS_LIMIT_PCT,
        weekly_drawdown_limit_pct: float = WEEKLY_DRAWDOWN_LIMIT_PCT,
        peak_drawdown_limit_pct: float = PEAK_DRAWDOWN_LIMIT_PCT,
        short_balance_threshold: float = STOCK_SHORT_BALANCE_THRESHOLD,
    ) -> None:
        self.max_positions = max_positions
        self.max_stock_positions = max_stock_positions
        self.max_crypto_positions = max_crypto_positions
        self.liquidity_position_pct = liquidity_position_pct
        self.max_total_capital_at_risk_pct = max_total_capital_at_risk_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.weekly_drawdown_limit_pct = weekly_drawdown_limit_pct
        self.peak_drawdown_limit_pct = peak_drawdown_limit_pct
        self.short_balance_threshold = short_balance_threshold

    def assess_trade(
        self,
        *,
        equity: float,
        stock_balance: float | None = None,
        daily_pnl_pct: float,
        weekly_drawdown_pct: float,
        peak_drawdown_pct: float,
        open_positions: Sequence[Position],
        candidate: Position,
        avg_daily_volume: float,
        correlation_lookup: Mapping[str, float] | None = None,
        correlation_limit: float = 0.7,
        max_position_slots: Mapping[str, int] | None = None,
    ) -> RiskAssessment:
        """Assess all core Phase 6 portfolio constraints."""

        reasons: list[str] = []
        max_slots = dict(max_position_slots or {
            "stock": self.max_stock_positions,
            "crypto": self.max_crypto_positions,
        })

        if len(open_positions) >= self.max_positions:
            reasons.append("maximum open positions reached")

        current_asset_positions = sum(
            1 for position in open_positions if position.asset_class == candidate.asset_class
        )
        if current_asset_positions >= max_slots.get(candidate.asset_class, self.max_positions):
            reasons.append(f"{candidate.asset_class} position slot limit reached")

        if daily_pnl_pct <= -self.daily_loss_limit_pct:
            reasons.append("daily loss limit hit")
        if weekly_drawdown_pct >= self.weekly_drawdown_limit_pct:
            reasons.append("weekly drawdown limit hit")
        if peak_drawdown_pct >= self.peak_drawdown_limit_pct:
            reasons.append("peak drawdown limit hit")

        if not self._passes_liquidity_check(candidate.size, avg_daily_volume):
            reasons.append("liquidity check failed")

        if not self._passes_capital_at_risk(equity, open_positions, candidate):
            reasons.append("capital at risk limit exceeded")

        if not self._passes_correlation_filter(
            candidate,
            open_positions,
            correlation_lookup,
            correlation_limit,
        ):
            reasons.append("correlation limit exceeded")

        if candidate.asset_class == "stock" and candidate.side == "short":
            if candidate.size <= 0.0:
                reasons.append("short position size must be positive")
            balance = equity if stock_balance is None else stock_balance
            if balance <= self.short_balance_threshold:
                reasons.append("short balance threshold not met")

        return RiskAssessment(allowed=not reasons, reasons=tuple(reasons))

    def _passes_liquidity_check(self, size: float, avg_daily_volume: float) -> bool:
        """Return True when the size is a small fraction of average volume."""

        if size <= 0.0 or avg_daily_volume <= 0.0:
            return False
        return size < avg_daily_volume * self.liquidity_position_pct

    def _passes_capital_at_risk(
        self,
        equity: float,
        open_positions: Sequence[Position],
        candidate: Position,
    ) -> bool:
        """Return True when total capital at risk stays below the configured cap."""

        if equity <= 0.0:
            return False
        total_at_risk = 0.0
        for position in open_positions:
            if position.sl_price is None:
                continue
            total_at_risk += abs(position.entry_price - position.sl_price) * position.size
        if candidate.sl_price is not None:
            total_at_risk += abs(candidate.entry_price - candidate.sl_price) * candidate.size
        return total_at_risk <= equity * self.max_total_capital_at_risk_pct

    def _passes_correlation_filter(
        self,
        candidate: Position,
        open_positions: Sequence[Position],
        correlation_lookup: Mapping[str, float] | None,
        correlation_limit: float,
    ) -> bool:
        """Return True when the candidate does not correlate too highly with open positions."""

        if correlation_lookup is None:
            return True
        for position in open_positions:
            key = self._pair_key(candidate.symbol, position.symbol)
            value = correlation_lookup.get(key)
            if value is None:
                continue
            if value > correlation_limit:
                return False
        return True

    def _pair_key(self, left: str, right: str) -> str:
        """Return a stable key for a pair of symbols."""

        ordered = sorted((left.upper(), right.upper()))
        return f"{ordered[0]}::{ordered[1]}"
