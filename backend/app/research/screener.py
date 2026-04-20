"""Quantitative screener scoring and filtering."""

from __future__ import annotations

from collections.abc import Sequence

from app.research.models import ScreeningMetrics

SCREENER_CRITERIA: dict[str, object] = {
    "min_avg_volume": 1_000_000.0,
    "min_price": 5.0,
    "max_price": 500.0,
    "min_market_cap": 2_000_000_000.0,
    "max_pe_ratio": 60.0,
    "min_relative_volume": 1.5,
    "float_min": 10_000_000.0,
    "sectors_allowed": [
        "Technology",
        "Healthcare",
        "Financials",
        "Consumer Discretionary",
        "Industrials",
        "Energy",
        "Communication Services",
        "Materials",
    ],
}


class StockScreenerService:
    """Score and filter stocks using daily screener metrics."""

    def passes_criteria(self, metrics: ScreeningMetrics) -> bool:
        """Return True when the symbol satisfies all screening rules."""

        if metrics.avg_volume < float(SCREENER_CRITERIA["min_avg_volume"]):
            return False
        if metrics.price < float(SCREENER_CRITERIA["min_price"]):
            return False
        if metrics.price > float(SCREENER_CRITERIA["max_price"]):
            return False
        if metrics.market_cap < float(SCREENER_CRITERIA["min_market_cap"]):
            return False
        max_pe_ratio = float(SCREENER_CRITERIA["max_pe_ratio"])
        if metrics.pe_ratio is not None and metrics.pe_ratio > max_pe_ratio:
            return False
        if metrics.relative_volume < float(SCREENER_CRITERIA["min_relative_volume"]):
            return False
        if metrics.float_shares < float(SCREENER_CRITERIA["float_min"]):
            return False
        if metrics.sector not in SCREENER_CRITERIA["sectors_allowed"]:
            return False
        if not metrics.above_50d_ema:
            return False
        return not metrics.earnings_blocked

    def score_candidate(self, metrics: ScreeningMetrics) -> float:
        """Return a normalized screener score between 0 and 1."""

        if not self.passes_criteria(metrics):
            return 0.0
        price_score = 1.0 - min(1.0, metrics.price / float(SCREENER_CRITERIA["max_price"]))
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
