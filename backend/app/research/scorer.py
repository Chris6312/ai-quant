"""Composite watchlist scoring."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.config.constants import DEFAULT_SIGNAL_WEIGHTS
from app.research.models import ResearchScoreBreakdown, SignalWeights


@dataclass(slots=True, frozen=True)
class WatchlistScore:
    """Represent a normalized watchlist score."""

    symbol: str
    score: float


class WatchlistScorer:
    """Combine Phase 2 research inputs into a composite score."""

    def __init__(self, weights: SignalWeights | None = None) -> None:
        self.weights = dict(weights or DEFAULT_SIGNAL_WEIGHTS)

    def score_breakdown(
        self,
        symbol: str,
        news_sentiment_7d: float,
        congress_buy: float,
        insider_buy: float,
        screener_pass: float,
        analyst_upgrade: float,
    ) -> ResearchScoreBreakdown:
        """Return a score breakdown and the composite score."""

        composite = self.score(
            news_sentiment_7d=news_sentiment_7d,
            congress_buy=congress_buy,
            insider_buy=insider_buy,
            screener_pass=screener_pass,
            analyst_upgrade=analyst_upgrade,
        )
        return ResearchScoreBreakdown(
            symbol=symbol,
            news_sentiment_7d=news_sentiment_7d,
            congress_buy=congress_buy,
            insider_buy=insider_buy,
            screener_pass=screener_pass,
            analyst_upgrade=analyst_upgrade,
            composite_score=composite,
        )

    def score(
        self,
        news_sentiment_7d: float,
        congress_buy: float,
        insider_buy: float,
        screener_pass: float,
        analyst_upgrade: float,
    ) -> float:
        """Return a weighted composite score in the 0-100 range."""

        composite = (
            news_sentiment_7d * self.weights["news_sentiment_7d"]
            + congress_buy * self.weights["congress_buy"]
            + insider_buy * self.weights["insider_buy"]
            + screener_pass * self.weights["screener_pass"]
            + analyst_upgrade * self.weights["analyst_upgrade"]
        )
        return max(0.0, min(100.0, composite * 100.0))

    def rank_breakdowns(
        self,
        breakdowns: Sequence[ResearchScoreBreakdown],
    ) -> list[ResearchScoreBreakdown]:
        """Sort breakdowns by composite score descending."""

        return sorted(breakdowns, key=lambda breakdown: breakdown.composite_score, reverse=True)
