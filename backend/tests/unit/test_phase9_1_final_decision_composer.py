"""Tests for Phase 9.1 final decision composer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from app.decision.composer import compose_dynamic_decision, compose_final_decision
from app.decision.visibility import (
    DecisionDirection,
    FinalSentimentDecision,
    FreshnessState,
    IntradayConfirmation,
    IntradayTrend,
    MacroSentimentDecision,
    MlBiasDecision,
    SentimentBias,
    SentimentDecisionMerge,
    SentimentEffect,
    SymbolSentimentDecision,
)


def _ml(
    *,
    direction: str,
    confidence: float | None = 0.65,
    freshness: str = "fresh",
) -> MlBiasDecision:
    return MlBiasDecision(
        direction=cast(DecisionDirection, direction),
        confidence=confidence,
        freshness=cast(FreshnessState, freshness),
    )


def _intraday(
    *,
    trend: str,
    breakout: bool = True,
    volume_expansion: bool = True,
) -> IntradayConfirmation:
    timeframes = ["15m", "1h"] if breakout or volume_expansion else []
    return IntradayConfirmation(
        trend=cast(IntradayTrend, trend),
        breakout=breakout,
        volume_expansion=volume_expansion,
        volatility_state="expanded",
        timeframes=timeframes,
    )


def _sentiment(
    *,
    macro_bias: str,
    symbol_bias: str,
    decision: str,
    effect: str,
    conflicts: list[str] | None = None,
) -> SentimentDecisionMerge:
    return SentimentDecisionMerge(
        macro_sentiment_bias=cast(SentimentBias, macro_bias),
        symbol_sentiment_bias=cast(SentimentBias, symbol_bias),
        final_sentiment_decision=cast(FinalSentimentDecision, decision),
        effect=cast(SentimentEffect, effect),
        reason="Sentiment test fixture.",
        conflicts=conflicts or [],
    )


def test_ml_bearish_intraday_bullish_stays_visible_as_reduced() -> None:
    """Daily bearish ML does not hard-block improving live structure."""

    decision = compose_final_decision(
        ml_bias=_ml(direction="short"),
        sentiment_merge=_sentiment(
            macro_bias="bearish",
            symbol_bias="bullish",
            decision="mixed",
            effect="headwind",
            conflicts=["macro_symbol_conflict"],
        ),
        intraday_confirmation=_intraday(trend="bullish"),
    )

    assert decision.action == "reduce"
    assert decision.direction == "long"
    assert decision.risk_mode == "reduced"
    assert decision.size_multiplier == 0.6
    assert "ml_direction_conflict" in decision.conflicts


def test_macro_bearish_symbol_bullish_technical_bullish_reduces_risk() -> None:
    """Local strength against bad market weather becomes reduced, not hidden."""

    decision = compose_final_decision(
        ml_bias=_ml(direction="long"),
        sentiment_merge=_sentiment(
            macro_bias="bearish",
            symbol_bias="bullish",
            decision="mixed",
            effect="headwind",
        ),
        intraday_confirmation=_intraday(trend="bullish"),
    )

    assert decision.action == "reduce"
    assert decision.direction == "long"
    assert decision.conflicts == ["sentiment_headwind"]


def test_macro_bearish_symbol_weak_technical_weak_blocks() -> None:
    """No local proof against bad market weather is a visible block."""

    decision = compose_final_decision(
        ml_bias=_ml(direction="short"),
        sentiment_merge=_sentiment(
            macro_bias="bearish",
            symbol_bias="neutral",
            decision="macro_headwind",
            effect="headwind",
        ),
        intraday_confirmation=_intraday(
            trend="bearish",
            breakout=False,
            volume_expansion=False,
        ),
    )

    assert decision.action == "block"
    assert decision.direction == "short"
    assert decision.size_multiplier == 0.0
    assert "weak_local_proof" in decision.conflicts


def test_aligned_bullish_layers_boost() -> None:
    """Macro bullish plus symbol bullish plus technical bullish can boost."""

    decision = compose_final_decision(
        ml_bias=_ml(direction="long", confidence=0.72),
        sentiment_merge=_sentiment(
            macro_bias="bullish",
            symbol_bias="bullish",
            decision="aligned",
            effect="tailwind",
        ),
        intraday_confirmation=_intraday(trend="bullish"),
    )

    assert decision.action == "boost"
    assert decision.direction == "long"
    assert decision.risk_mode == "boosted"
    assert decision.size_multiplier == 1.1


def test_ml_skip_strong_intraday_setup_becomes_watch() -> None:
    """ML skip does not make a strong closed-candle setup invisible."""

    decision = compose_final_decision(
        ml_bias=_ml(direction="unknown", confidence=None, freshness="missing"),
        sentiment_merge=_sentiment(
            macro_bias="neutral",
            symbol_bias="bullish",
            decision="symbol_tailwind",
            effect="tailwind",
        ),
        intraday_confirmation=_intraday(trend="bullish"),
    )

    assert decision.action == "watch"
    assert decision.direction == "long"
    assert decision.risk_mode == "watch_only"
    assert "ml_skip" in decision.conflicts


def test_composer_returns_full_dynamic_decision_envelope() -> None:
    """Slice 4 returns the same envelope Research will later display."""

    generated_at = datetime(2026, 4, 26, 17, 40, tzinfo=UTC)
    decision = compose_dynamic_decision(
        symbol="SOL/USD",
        ml_bias=_ml(direction="long"),
        macro_sentiment=MacroSentimentDecision(
            bias="bullish",
            score=0.18,
            effect="tailwind",
            article_count=20,
            source_symbols=["BTC/USD", "ETH/USD"],
            as_of=generated_at,
        ),
        symbol_sentiment=SymbolSentimentDecision(
            bias="bullish",
            score=0.24,
            article_count=8,
            as_of=generated_at,
        ),
        sentiment_merge=_sentiment(
            macro_bias="bullish",
            symbol_bias="bullish",
            decision="aligned",
            effect="tailwind",
        ),
        intraday_confirmation=_intraday(trend="bullish"),
        generated_at=generated_at,
    )

    assert decision.symbol == "SOL/USD"
    assert decision.final_decision.action == "boost"
    assert decision.generated_at == generated_at
