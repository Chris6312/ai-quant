"""Sentiment merge helpers for Phase 9.1 decision visibility.

This module turns persisted BTC/ETH macro sentiment and optional symbol-level
sentiment into UI-ready decision context. It does not execute trades and does
not treat BTC/ETH weather as a hard universal block.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from app.db.models import CryptoDailySentimentRow
from app.decision.visibility import (
    MacroSentimentDecision,
    SentimentBias,
    SentimentDecisionMerge,
    SentimentEffect,
    SymbolSentimentDecision,
)
from app.ml.macro_sentiment import DailyMacroSentimentSource, blend_daily_macro_sentiment

BULLISH_SENTIMENT_THRESHOLD: Final[float] = 0.10
BEARISH_SENTIMENT_THRESHOLD: Final[float] = -0.10
WEAK_COVERAGE_ARTICLE_THRESHOLD: Final[int] = 3
BTC_MACRO_SYMBOL: Final[str] = "BTC/USD"
ETH_MACRO_SYMBOL: Final[str] = "ETH/USD"


def build_macro_sentiment_decision(
    *,
    btc_row: CryptoDailySentimentRow | None,
    eth_row: CryptoDailySentimentRow | None,
) -> MacroSentimentDecision:
    """Build BTC/ETH macro weather for crypto decisions.

    BTC and ETH rows are blended with the existing ML macro-sentiment weighting.
    The result is weather only: bearish macro sentiment becomes a headwind, not
    an automatic block for every altcoin.
    """

    sources = _macro_sources(btc_row=btc_row, eth_row=eth_row)
    score = blend_daily_macro_sentiment(
        btc_row=sources.get(BTC_MACRO_SYMBOL),
        eth_row=sources.get(ETH_MACRO_SYMBOL),
    )
    article_count = sum(_safe_article_count(row) for row in (btc_row, eth_row))
    bias = classify_sentiment_bias(score)
    return MacroSentimentDecision(
        bias=bias,
        score=score,
        effect=_macro_effect_for_bias(bias),
        article_count=article_count,
        source_symbols=list(sources),
        as_of=_latest_updated_at(btc_row, eth_row),
    )


def build_symbol_sentiment_decision(
    row: CryptoDailySentimentRow | None,
) -> SymbolSentimentDecision:
    """Build local symbol sentiment forecast from one persisted daily row."""

    if row is None:
        return SymbolSentimentDecision(bias="unknown")

    score = row.compound_score
    return SymbolSentimentDecision(
        bias=classify_sentiment_bias(score),
        score=score,
        article_count=_safe_article_count(row),
        as_of=row.updated_at,
    )


def merge_sentiment_decisions(
    *,
    macro_sentiment: MacroSentimentDecision,
    symbol_sentiment: SymbolSentimentDecision,
) -> SentimentDecisionMerge:
    """Merge macro weather and symbol forecast without hiding conflicts."""

    macro_bias = macro_sentiment.bias
    symbol_bias = symbol_sentiment.bias
    conflicts: list[str] = []

    if macro_bias == "unknown" and symbol_bias == "unknown":
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="unknown",
            effect="unknown",
            reason="No macro or symbol sentiment is available yet.",
        )

    if _has_weak_coverage(macro_sentiment, symbol_sentiment):
        conflicts.append("weak_sentiment_coverage")

    if macro_bias in {"bullish", "bearish"} and symbol_bias in {"bullish", "bearish"}:
        if macro_bias == symbol_bias:
            return SentimentDecisionMerge(
                macro_sentiment_bias=macro_bias,
                symbol_sentiment_bias=symbol_bias,
                final_sentiment_decision="aligned",
                effect=_macro_effect_for_bias(macro_bias),
                reason="Macro weather and symbol forecast point in the same direction.",
                conflicts=conflicts,
            )
        conflicts.append("macro_symbol_conflict")
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="mixed",
            effect="headwind" if macro_bias == "bearish" else "tailwind",
            reason="Symbol sentiment conflicts with BTC/ETH macro weather; keep it visible.",
            conflicts=conflicts,
        )

    if macro_bias == "bearish":
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="macro_headwind",
            effect="headwind",
            reason=(
                "BTC/ETH macro sentiment is bearish, so risk should be reduced "
                "unless local proof improves."
            ),
            conflicts=conflicts,
        )

    if macro_bias == "bullish":
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="macro_tailwind",
            effect="tailwind",
            reason="BTC/ETH macro sentiment is bullish, so crypto risk has a tailwind.",
            conflicts=conflicts,
        )

    if symbol_bias == "bullish":
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="symbol_tailwind",
            effect="tailwind",
            reason="Symbol sentiment is bullish while macro weather is not blocking the setup.",
            conflicts=conflicts,
        )

    if symbol_bias == "bearish":
        return SentimentDecisionMerge(
            macro_sentiment_bias=macro_bias,
            symbol_sentiment_bias=symbol_bias,
            final_sentiment_decision="symbol_headwind",
            effect="headwind",
            reason=(
                "Symbol sentiment is bearish even though macro weather is not "
                "strongly bearish."
            ),
            conflicts=conflicts,
        )

    return SentimentDecisionMerge(
        macro_sentiment_bias=macro_bias,
        symbol_sentiment_bias=symbol_bias,
        final_sentiment_decision="neutral",
        effect="neutral",
        reason="Sentiment is neutral or non-directional.",
        conflicts=conflicts,
    )


def classify_sentiment_bias(score: float | None) -> SentimentBias:
    """Classify a normalized compound sentiment score for decision visibility."""

    if score is None:
        return "unknown"
    if score >= BULLISH_SENTIMENT_THRESHOLD:
        return "bullish"
    if score <= BEARISH_SENTIMENT_THRESHOLD:
        return "bearish"
    return "neutral"


def _macro_sources(
    *,
    btc_row: CryptoDailySentimentRow | None,
    eth_row: CryptoDailySentimentRow | None,
) -> dict[str, DailyMacroSentimentSource]:
    sources: dict[str, DailyMacroSentimentSource] = {}
    for row in (btc_row, eth_row):
        if row is None:
            continue
        source = DailyMacroSentimentSource(
            symbol=row.symbol.upper(),
            sentiment_date=row.sentiment_date,
            compound_score=row.compound_score,
            article_count=_safe_article_count(row),
            coverage_score=max(0.0, row.coverage_score),
        )
        sources[source.symbol] = source
    return sources


def _macro_effect_for_bias(bias: SentimentBias) -> SentimentEffect:
    if bias == "bullish":
        return "tailwind"
    if bias == "bearish":
        return "headwind"
    if bias == "neutral":
        return "neutral"
    return "unknown"


def _safe_article_count(row: CryptoDailySentimentRow | None) -> int:
    if row is None:
        return 0
    return max(0, row.article_count)


def _latest_updated_at(*rows: CryptoDailySentimentRow | None) -> datetime | None:
    updated_values = [row.updated_at for row in rows if row is not None]
    if not updated_values:
        return None
    return max(updated_values)


def _has_weak_coverage(
    macro_sentiment: MacroSentimentDecision,
    symbol_sentiment: SymbolSentimentDecision,
) -> bool:
    macro_missing = macro_sentiment.article_count < WEAK_COVERAGE_ARTICLE_THRESHOLD
    symbol_missing = symbol_sentiment.article_count < WEAK_COVERAGE_ARTICLE_THRESHOLD
    return macro_missing and symbol_missing
