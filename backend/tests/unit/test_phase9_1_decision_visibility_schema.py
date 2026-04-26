"""Tests for Phase 9.1 dynamic decision visibility schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.decision.visibility import (
    DynamicDecision,
    FinalDecision,
    IntradayConfirmation,
    MacroSentimentDecision,
    MlBiasDecision,
    SymbolSentimentDecision,
    build_no_trade_decision,
)


def test_dynamic_decision_accepts_ml_conflict_as_watch() -> None:
    """Daily bearish ML plus bullish intraday proof can remain visible as watch."""

    generated_at = datetime(2026, 4, 26, 16, 45, tzinfo=UTC)
    decision = DynamicDecision(
        symbol="SOL/USD",
        ml_bias=MlBiasDecision(direction="short", confidence=0.63, freshness="fresh"),
        macro_sentiment=MacroSentimentDecision(
            bias="bearish",
            score=-0.12,
            effect="headwind",
            article_count=25,
            source_symbols=["BTC/USD", "ETH/USD"],
            as_of=generated_at,
        ),
        symbol_sentiment=SymbolSentimentDecision(
            bias="bullish",
            score=0.34,
            article_count=18,
            as_of=generated_at,
        ),
        intraday_confirmation=IntradayConfirmation(
            trend="bullish",
            breakout=True,
            volume_expansion=True,
            volatility_state="expanded",
            timeframes=["15m", "1h"],
            as_of=generated_at,
        ),
        final_decision=FinalDecision(
            action="watch",
            direction="long",
            risk_mode="watch_only",
            size_multiplier=0.0,
            reason="Intraday bullish confirmation conflicts with bearish daily ML bias.",
            conflicts=["ml_bias", "macro_headwind"],
        ),
        generated_at=generated_at,
    )

    assert decision.final_decision.action == "watch"
    assert decision.ml_bias.direction == "short"
    assert decision.intraday_confirmation.timeframes == ["15m", "1h"]


def test_block_and_no_trade_must_have_zero_size() -> None:
    """Blocked decision states cannot accidentally carry exposure sizing."""

    with pytest.raises(ValidationError):
        FinalDecision(
            action="block",
            direction="long",
            risk_mode="blocked",
            size_multiplier=0.5,
            reason="Macro and technical layers are both weak.",
        )


@pytest.mark.parametrize(
    ("action", "risk_mode"),
    [
        ("boost", "normal"),
        ("reduce", "normal"),
    ],
)
def test_action_requires_matching_risk_mode(action: str, risk_mode: str) -> None:
    """UI labels stay synchronized with action semantics."""

    with pytest.raises(ValidationError):
        FinalDecision(
            action=action,
            direction="long",
            risk_mode=risk_mode,
            size_multiplier=0.5,
            reason="Invalid action/risk-mode pairing.",
        )


def test_intraday_proof_requires_timeframe_labels() -> None:
    """Closed-candle proof must name the timeframe lane behind it."""

    with pytest.raises(ValidationError):
        IntradayConfirmation(
            trend="bullish",
            breakout=True,
            volume_expansion=False,
            timeframes=[],
        )


def test_build_no_trade_decision_is_visible_empty_state() -> None:
    """No-trade helper creates an explicit visible decision instead of hiding rows."""

    generated_at = datetime(2026, 4, 26, 17, 0, tzinfo=UTC)
    decision = build_no_trade_decision(
        symbol="ETH/USD",
        reason="No valid closed-candle setup is available.",
        generated_at=generated_at,
    )

    assert decision.symbol == "ETH/USD"
    assert decision.final_decision.action == "no_trade"
    assert decision.final_decision.size_multiplier == 0.0
    assert decision.generated_at == generated_at
