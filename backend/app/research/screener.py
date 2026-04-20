"""Quantitative screener scoring and filtering."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.research.models import ScreeningMetrics

MIN_AVG_VOLUME: Final[float] = 1_000_000.0
MIN_PRICE: Final[float] = 5.0
MAX_PRICE: Final[float] = 500.0
MIN_MARKET_CAP: Final[float] = 2_000_000_000.0
MAX_PE_RATIO: Final[float] = 60.0
MIN_RELATIVE_VOLUME: Final[float] = 1.5
FLOAT_MIN: Final[float] = 10_000_000.0
SECTORS_ALLOWED: Final[tuple[str, ...]] = (
    "Technology",
    "Healthcare",
    "Financials",
    "Consumer Discretionary",
    "Industrials",
    "Energy",
    "Communication Services",
    "Materials",
)


class StockScreenerService:
    """Score and filter stocks using daily screener metrics."""

    def passes_criteria(self, metrics: ScreeningMetrics) -> bool:
        """Return True when the symbol satisfies all screening rules."""

        if metrics.avg_volume < MIN_AVG_VOLUME:
            return False
        if metrics.price < MIN_PRICE:
            return False
        if metrics.price > MAX_PRICE:
            return False
        if metrics.market_cap < MIN_MARKET_CAP:
            return False
        if metrics.pe_ratio is not None and metrics.pe_ratio > MAX_PE_RATIO:
            return False
        if metrics.relative_volume < MIN_RELATIVE_VOLUME:
            return False
        if metrics.float_shares < FLOAT_MIN:
            return False
        if metrics.sector not in SECTORS_ALLOWED:
            return False
        if not metrics.above_50d_ema:
            return False
        return not metrics.earnings_blocked

    def score_candidate(self, metrics: ScreeningMetrics) -> float:
        """Return a normalized screener score between 0 and 1."""

        if not self.passes_criteria(metrics):
            return 0.0
        price_score = 1.0 - min(1.0, metrics.price / MAX_PRICE)
        volume_score = min(1.0, metrics.relative_volume / 5.0)
        cap_score = min(1.0, metrics.market_cap / 10_000_000_000.0)
        return max(0.0, min(1.0, (price_score + volume_score + cap_score) / 3.0))

    def rank_candidates(
        self,
        candidates: Sequence[ScreeningMetrics],
    ) -> list[tuple[ScreeningMetrics, float]]:
        """Rank candidates by screener score descending."""

        scored = [(candidate, self.score_candidate(candidate)) for candidate in candidates]
        return sorted(scored, key=lambda item: item[1], reverse=True)
