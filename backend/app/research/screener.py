"""Quantitative screener scoring and filtering."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from app.config.constants import (
    SCREENER_ALLOWED_SECTORS,
    SCREENER_MAX_PE_RATIO,
    SCREENER_MAX_PRICE,
    SCREENER_MIN_AVG_VOLUME,
    SCREENER_MIN_FLOAT_SHARES,
    SCREENER_MIN_MARKET_CAP,
    SCREENER_MIN_PRICE,
    SCREENER_MIN_RELATIVE_VOLUME,
)
from app.db.models import ResearchSignalRow
from app.research.models import ScreeningMetrics, utc_now


class StockScreenerService:
    """Score and filter stocks using daily screener metrics."""

    def passes_criteria(self, metrics: ScreeningMetrics) -> bool:
        """Return True when the symbol satisfies all screening rules."""

        if metrics.avg_volume < SCREENER_MIN_AVG_VOLUME:
            return False
        if metrics.price < SCREENER_MIN_PRICE:
            return False
        if metrics.price > SCREENER_MAX_PRICE:
            return False
        if metrics.market_cap < SCREENER_MIN_MARKET_CAP:
            return False
        if metrics.pe_ratio is not None and metrics.pe_ratio > SCREENER_MAX_PE_RATIO:
            return False
        if metrics.relative_volume < SCREENER_MIN_RELATIVE_VOLUME:
            return False
        if metrics.float_shares < SCREENER_MIN_FLOAT_SHARES:
            return False
        if metrics.sector not in SCREENER_ALLOWED_SECTORS:
            return False
        if not metrics.above_50d_ema:
            return False
        return not metrics.earnings_blocked

    def score_candidate(self, metrics: ScreeningMetrics) -> float:
        """Return a normalized screener score between 0 and 1."""

        if not self.passes_criteria(metrics):
            return 0.0
        price_score = 1.0 - min(1.0, metrics.price / SCREENER_MAX_PRICE)
        volume_score = min(1.0, metrics.relative_volume / 5.0)
        cap_score = min(1.0, metrics.market_cap / 10_000_000_000.0)
        return max(0.0, min(1.0, (price_score + volume_score + cap_score) / 3.0))

    def build_signal_row(self, metrics: ScreeningMetrics) -> ResearchSignalRow:
        """Build a screener research signal for one candidate."""

        score = self.score_candidate(metrics)
        return ResearchSignalRow(
            id=str(uuid4()),
            symbol=metrics.symbol,
            signal_type="screener",
            score=score,
            direction="bullish" if score > 0.0 else "neutral",
            source="quant_screener",
            raw_data={
                "avg_volume": metrics.avg_volume,
                "price": metrics.price,
                "market_cap": metrics.market_cap,
                "pe_ratio": metrics.pe_ratio,
                "relative_volume": metrics.relative_volume,
                "float_shares": metrics.float_shares,
                "sector": metrics.sector,
                "above_50d_ema": metrics.above_50d_ema,
                "earnings_blocked": metrics.earnings_blocked,
            },
            created_at=utc_now(),
        )

    def rank_candidates(
        self,
        candidates: Sequence[ScreeningMetrics],
    ) -> list[tuple[ScreeningMetrics, float]]:
        """Rank candidates by screener score descending."""

        scored = [(candidate, self.score_candidate(candidate)) for candidate in candidates]
        return sorted(scored, key=lambda item: item[1], reverse=True)
