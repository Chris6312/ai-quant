"""Final decision composer for Phase 9.1 dynamic decision visibility.

The composer joins daily ML bias, sentiment weather, and closed-candle intraday
proof into one visible decision object. It intentionally does not execute trades,
change paper state, rerun ML intraday, or fetch open candles.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from app.decision.visibility import (
    DecisionAction,
    DecisionDirection,
    DecisionRiskMode,
    DynamicDecision,
    FinalDecision,
    IntradayConfirmation,
    MacroSentimentDecision,
    MlBiasDecision,
    SentimentDecisionMerge,
    SymbolSentimentDecision,
)

STRONG_ML_CONFIDENCE: Final[float] = 0.60
ALLOW_SIZE_MULTIPLIER: Final[float] = 1.0
BOOST_SIZE_MULTIPLIER: Final[float] = 1.1
REDUCED_SIZE_MULTIPLIER: Final[float] = 0.6
ZERO_SIZE_MULTIPLIER: Final[float] = 0.0


def compose_dynamic_decision(
    *,
    symbol: str,
    ml_bias: MlBiasDecision,
    macro_sentiment: MacroSentimentDecision,
    symbol_sentiment: SymbolSentimentDecision,
    sentiment_merge: SentimentDecisionMerge,
    intraday_confirmation: IntradayConfirmation,
    generated_at: datetime,
) -> DynamicDecision:
    """Compose the visible decision envelope for Research.

    The decision is intentionally conservative. Daily ML conflicts, macro
    headwinds, and weak sentiment coverage stay visible in conflicts/reason text
    instead of silently hiding candidates.
    """

    final_decision = compose_final_decision(
        ml_bias=ml_bias,
        sentiment_merge=sentiment_merge,
        intraday_confirmation=intraday_confirmation,
    )
    return DynamicDecision(
        symbol=symbol,
        ml_bias=ml_bias,
        macro_sentiment=macro_sentiment,
        symbol_sentiment=symbol_sentiment,
        intraday_confirmation=intraday_confirmation,
        final_decision=final_decision,
        generated_at=generated_at,
    )


def compose_final_decision(
    *,
    ml_bias: MlBiasDecision,
    sentiment_merge: SentimentDecisionMerge,
    intraday_confirmation: IntradayConfirmation,
) -> FinalDecision:
    """Return the final visibility decision from already-built layer objects."""

    setup_direction = _direction_from_intraday(intraday_confirmation)
    conflicts = _base_conflicts(
        ml_bias=ml_bias,
        sentiment_merge=sentiment_merge,
        setup_direction=setup_direction,
    )

    if setup_direction == "unknown":
        return FinalDecision(
            action="no_trade",
            direction="unknown",
            risk_mode="blocked",
            size_multiplier=ZERO_SIZE_MULTIPLIER,
            reason="No closed-candle intraday setup is available yet.",
            conflicts=conflicts,
        )

    technical_strength = _technical_strength(intraday_confirmation)
    if _should_block_weak_setup(
        sentiment_merge=sentiment_merge,
        intraday_confirmation=intraday_confirmation,
        technical_strength=technical_strength,
    ):
        return _decision(
            action="block",
            direction=setup_direction,
            reason=(
                "No local technical proof is strong enough against "
                "bearish sentiment weather."
            ),
            conflicts=[*conflicts, "weak_local_proof"],
        )

    if _ml_is_skip(ml_bias):
        return _decision(
            action="watch",
            direction=setup_direction,
            reason=(
                "ML bias is unavailable or not fresh, but closed-candle "
                "intraday proof exists."
            ),
            conflicts=[*conflicts, "ml_skip"],
        )

    if _ml_conflicts_with_setup(ml_bias, setup_direction):
        return _decision(
            action="reduce",
            direction=setup_direction,
            reason=(
                "Intraday confirmation conflicts with daily ML bias, "
                "so keep the candidate visible with reduced risk."
            ),
            conflicts=[*conflicts, "ml_direction_conflict"],
        )

    if sentiment_merge.final_sentiment_decision in {"macro_headwind", "mixed"}:
        return _decision(
            action="reduce",
            direction=setup_direction,
            reason=(
                "Local proof exists, but BTC/ETH macro weather remains "
                "a risk headwind."
            ),
            conflicts=conflicts,
        )

    if _has_full_bullish_alignment(
        ml_bias=ml_bias,
        sentiment_merge=sentiment_merge,
        intraday_confirmation=intraday_confirmation,
        setup_direction=setup_direction,
    ):
        return _decision(
            action="boost",
            direction=setup_direction,
            reason=(
                "ML bias, sentiment weather, and closed-candle technical "
                "proof are aligned."
            ),
            conflicts=conflicts,
        )

    if _has_valid_setup(technical_strength):
        return _decision(
            action="allow",
            direction=setup_direction,
            reason=(
                "Closed-candle intraday proof supports the setup without "
                "a major blocking layer."
            ),
            conflicts=conflicts,
        )

    return _decision(
        action="watch",
        direction=setup_direction,
        reason="A directional setup exists, but confirmation is still light.",
        conflicts=conflicts,
    )


def _decision(
    *,
    action: DecisionAction,
    direction: DecisionDirection,
    reason: str,
    conflicts: list[str],
) -> FinalDecision:
    return FinalDecision(
        action=action,
        direction=direction,
        risk_mode=_risk_mode_for_action(action),
        size_multiplier=_size_multiplier_for_action(action),
        reason=reason,
        conflicts=_deduplicate(conflicts),
    )


def _direction_from_intraday(
    intraday_confirmation: IntradayConfirmation,
) -> DecisionDirection:
    if intraday_confirmation.trend == "bullish":
        return "long"
    if intraday_confirmation.trend == "bearish":
        return "short"
    return "unknown"


def _technical_strength(intraday_confirmation: IntradayConfirmation) -> int:
    strength = 0
    if intraday_confirmation.trend in {"bullish", "bearish"}:
        strength += 1
    if len(intraday_confirmation.timeframes) >= 2:
        strength += 1
    if intraday_confirmation.breakout:
        strength += 1
    if intraday_confirmation.volume_expansion:
        strength += 1
    return strength


def _has_valid_setup(technical_strength: int) -> bool:
    return technical_strength >= 2


def _should_block_weak_setup(
    *,
    sentiment_merge: SentimentDecisionMerge,
    intraday_confirmation: IntradayConfirmation,
    technical_strength: int,
) -> bool:
    weak_or_bearish_technical = technical_strength < 2
    sentiment_is_weak = sentiment_merge.final_sentiment_decision in {
        "macro_headwind",
        "symbol_headwind",
        "neutral",
        "unknown",
    }
    return (
        sentiment_merge.macro_sentiment_bias == "bearish"
        and sentiment_is_weak
        and weak_or_bearish_technical
    )


def _ml_is_skip(ml_bias: MlBiasDecision) -> bool:
    return ml_bias.freshness != "fresh" or ml_bias.direction in {"neutral", "unknown"}


def _ml_conflicts_with_setup(
    ml_bias: MlBiasDecision,
    setup_direction: DecisionDirection,
) -> bool:
    if ml_bias.direction == "long" and setup_direction == "short":
        return True
    return ml_bias.direction == "short" and setup_direction == "long"


def _has_full_bullish_alignment(
    *,
    ml_bias: MlBiasDecision,
    sentiment_merge: SentimentDecisionMerge,
    intraday_confirmation: IntradayConfirmation,
    setup_direction: DecisionDirection,
) -> bool:
    return (
        setup_direction == "long"
        and ml_bias.direction == "long"
        and ml_bias.freshness == "fresh"
        and (ml_bias.confidence or 0.0) >= STRONG_ML_CONFIDENCE
        and sentiment_merge.final_sentiment_decision == "aligned"
        and sentiment_merge.effect == "tailwind"
        and intraday_confirmation.trend == "bullish"
        and intraday_confirmation.breakout
        and intraday_confirmation.volume_expansion
    )


def _base_conflicts(
    *,
    ml_bias: MlBiasDecision,
    sentiment_merge: SentimentDecisionMerge,
    setup_direction: DecisionDirection,
) -> list[str]:
    conflicts = list(sentiment_merge.conflicts)
    if sentiment_merge.effect == "headwind":
        conflicts.append("sentiment_headwind")
    if _ml_conflicts_with_setup(ml_bias, setup_direction):
        conflicts.append("ml_direction_conflict")
    if ml_bias.freshness != "fresh":
        conflicts.append("ml_not_fresh")
    return _deduplicate(conflicts)


def _risk_mode_for_action(action: DecisionAction) -> DecisionRiskMode:
    if action == "boost":
        return "boosted"
    if action == "reduce":
        return "reduced"
    if action in {"block", "no_trade"}:
        return "blocked"
    if action == "watch":
        return "watch_only"
    return "normal"


def _size_multiplier_for_action(action: DecisionAction) -> float:
    if action == "boost":
        return BOOST_SIZE_MULTIPLIER
    if action == "allow":
        return ALLOW_SIZE_MULTIPLIER
    if action == "reduce":
        return REDUCED_SIZE_MULTIPLIER
    return ZERO_SIZE_MULTIPLIER


def _deduplicate(values: list[str]) -> list[str]:
    deduplicated: list[str] = []
    for value in values:
        if value not in deduplicated:
            deduplicated.append(value)
    return deduplicated
