"""Blend BTC and ETH daily sentiment rows into shared crypto macro features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

BTC_MACRO_SENTIMENT_WEIGHT: float = 0.7
ETH_MACRO_SENTIMENT_WEIGHT: float = 0.3


@dataclass(frozen=True, slots=True)
class DailyMacroSentimentSource:
    """One source-backed daily sentiment row used by the crypto macro blend."""

    symbol: str
    sentiment_date: date
    compound_score: float | None
    article_count: int
    coverage_score: float


@dataclass(frozen=True, slots=True)
class MacroSentimentFeatures:
    """Shared crypto macro sentiment features for one training or prediction date."""

    sentiment_date: date
    news_sentiment_1d: float | None
    news_sentiment_7d: float | None
    news_article_count_7d: int


def blend_daily_macro_sentiment(
    *,
    btc_row: DailyMacroSentimentSource | None,
    eth_row: DailyMacroSentimentSource | None,
) -> float | None:
    """Return a coverage-weighted BTC/ETH blended daily sentiment score."""

    weighted_score_sum = 0.0
    weight_sum = 0.0

    if btc_row is not None and btc_row.compound_score is not None:
        btc_weight = BTC_MACRO_SENTIMENT_WEIGHT * max(0.0, btc_row.coverage_score)
        weighted_score_sum += btc_row.compound_score * btc_weight
        weight_sum += btc_weight

    if eth_row is not None and eth_row.compound_score is not None:
        eth_weight = ETH_MACRO_SENTIMENT_WEIGHT * max(0.0, eth_row.coverage_score)
        weighted_score_sum += eth_row.compound_score * eth_weight
        weight_sum += eth_weight

    if weight_sum <= 0.0:
        return None
    return weighted_score_sum / weight_sum


def build_macro_sentiment_features(
    *,
    sentiment_date: date,
    btc_rows: list[DailyMacroSentimentSource],
    eth_rows: list[DailyMacroSentimentSource],
) -> MacroSentimentFeatures:
    """Build the 1d and 7d shared macro sentiment features for one date."""

    btc_today = _row_for_date(btc_rows, sentiment_date)
    eth_today = _row_for_date(eth_rows, sentiment_date)
    one_day = blend_daily_macro_sentiment(btc_row=btc_today, eth_row=eth_today)

    seven_day_scores: list[float] = []
    for row_date in sorted({row.sentiment_date for row in btc_rows + eth_rows}):
        if not 0 <= (sentiment_date - row_date).days <= 6:
            continue
        btc_row = _row_for_date(btc_rows, row_date)
        eth_row = _row_for_date(eth_rows, row_date)
        daily_score = blend_daily_macro_sentiment(btc_row=btc_row, eth_row=eth_row)
        if daily_score is not None:
            seven_day_scores.append(daily_score)

    article_count = sum(
        max(0, row.article_count)
        for row in btc_rows + eth_rows
        if 0 <= (sentiment_date - row.sentiment_date).days <= 6
    )

    return MacroSentimentFeatures(
        sentiment_date=sentiment_date,
        news_sentiment_1d=one_day,
        news_sentiment_7d=_average(seven_day_scores),
        news_article_count_7d=article_count,
    )


def _row_for_date(
    rows: list[DailyMacroSentimentSource],
    target_date: date,
) -> DailyMacroSentimentSource | None:
    """Return the row for target_date when it exists."""

    for row in rows:
        if row.sentiment_date == target_date:
            return row
    return None


def _average(values: list[float]) -> float | None:
    """Return the arithmetic mean, preserving missingness when no values exist."""

    if not values:
        return None
    return sum(values) / float(len(values))