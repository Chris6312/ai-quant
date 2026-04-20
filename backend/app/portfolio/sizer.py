"""Position sizing utilities for Phase 6."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.constants import (
    MAX_SINGLE_POSITION_PCT,
    RESEARCH_SCORE_BONUS_1,
    RESEARCH_SCORE_BONUS_2,
    RESEARCH_SCORE_BONUS_THRESHOLD_1,
    RESEARCH_SCORE_BONUS_THRESHOLD_2,
)


@dataclass(slots=True, frozen=True)
class SizerConfig:
    """Configure base position sizing parameters."""

    risk_pct: float = 0.01
    max_position_pct: float = MAX_SINGLE_POSITION_PCT


class PositionSizer:
    """Calculate position size using ATR, ML confidence, research, and Kelly."""

    def __init__(self, config: SizerConfig | None = None) -> None:
        self.config = config or SizerConfig()

    def calculate(
        self,
        equity: float,
        entry_price: float,
        sl_price: float,
        ml_confidence: float,
        research_score: float = 0.0,
        asset_class: str = "stock",
        edge: float | None = None,
        odds: float | None = None,
    ) -> float:
        """Return the final position size after all caps and multipliers."""

        return calculate_position_size(
            equity=equity,
            entry_price=entry_price,
            sl_price=sl_price,
            ml_confidence=ml_confidence,
            research_score=research_score,
            asset_class=asset_class,
            risk_pct=self.config.risk_pct,
            max_position_pct=self.config.max_position_pct,
            edge=edge,
            odds=odds,
        )


def calculate_position_size(
    equity: float,
    entry_price: float,
    sl_price: float,
    ml_confidence: float,
    research_score: float = 0.0,
    asset_class: str = "stock",
    risk_pct: float = 0.01,
    max_position_pct: float = MAX_SINGLE_POSITION_PCT,
    edge: float | None = None,
    odds: float | None = None,
) -> float:
    """Calculate a capped position size.

    The result is the minimum of:
    - ATR-based size
    - quarter-Kelly size, when `edge` and `odds` are provided
    - hard max position cap
    """

    sl_distance = abs(entry_price - sl_price)
    if sl_distance <= 0.0 or equity <= 0.0 or entry_price <= 0.0:
        return 0.0

    base_size = (equity * risk_pct) / sl_distance
    confidence_scalar = max(0.6, min(1.0, ml_confidence))

    research_bonus = 1.0
    if asset_class == "stock":
        if research_score >= RESEARCH_SCORE_BONUS_THRESHOLD_2:
            research_bonus = RESEARCH_SCORE_BONUS_2
        elif research_score >= RESEARCH_SCORE_BONUS_THRESHOLD_1:
            research_bonus = RESEARCH_SCORE_BONUS_1

    atr_sized = base_size * confidence_scalar * research_bonus
    max_size = (equity * max_position_pct) / entry_price
    candidates = [atr_sized, max_size]

    if edge is not None and odds is not None and odds > 0.0:
        kelly_size = equity * (edge / odds) * 0.25
        candidates.append(kelly_size)

    return max(0.0, min(candidates))
