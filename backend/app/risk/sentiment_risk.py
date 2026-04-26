"""Sentiment risk-pressure controls for ML-driven crypto trade candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TradeDirection = Literal["long", "short"]
SentimentBias = Literal["bullish", "bearish", "neutral", "unknown"]
SentimentGateState = Literal["allowed", "blocked", "downgraded"]
SentimentRiskFlag = Literal[
    "aligned",
    "extreme_macro_pressure",
    "macro_pressure",
    "weak_coverage",
    "neutral",
    "missing_sentiment",
]


@dataclass(frozen=True, slots=True)
class SentimentGateInput:
    """Inputs needed to evaluate macro sentiment pressure for a trade candidate.

    Phase 9 intentionally treats BTC/ETH sentiment as a crypto macro layer. It is
    not symbol-specific altcoin sentiment, so normal bearish/bullish conflict
    downgrades risk instead of universally blocking otherwise strong setups.
    """

    direction: TradeDirection
    news_sentiment_1d: float | None
    article_count_7d: int
    model_confidence: float | None = None
    bearish_pressure_threshold: float = -0.30
    bullish_pressure_threshold: float = 0.30
    bearish_extreme_threshold: float = -0.60
    bullish_extreme_threshold: float = 0.60
    weak_confidence_threshold: float = 0.55
    moderate_confidence_threshold: float = 0.65
    min_article_count_7d: int = 3


@dataclass(frozen=True, slots=True)
class SentimentGateDecision:
    """Result of macro sentiment risk-pressure evaluation."""

    state: SentimentGateState
    allowed: bool
    sentiment_bias: SentimentBias
    risk_flag: SentimentRiskFlag
    reason: str


@dataclass(frozen=True, slots=True)
class SentimentSizingInput:
    """Sizing policy for sentiment risk-pressure decisions.

    This calculates a multiplier only. It does not place trades and does not
    change account risk by itself. Execution/pre-trade layers must explicitly
    consume the multiplier in a later Phase 9 slice.
    """

    decision: SentimentGateDecision
    base_multiplier: float = 1.0
    aligned_multiplier: float = 1.10
    macro_pressure_multiplier: float = 0.75
    extreme_macro_pressure_multiplier: float = 0.50
    weak_coverage_multiplier: float = 0.75
    missing_sentiment_multiplier: float = 0.75
    neutral_multiplier: float = 1.0
    minimum_multiplier: float = 0.0
    maximum_multiplier: float = 1.25


@dataclass(frozen=True, slots=True)
class SentimentConfidenceInput:
    """Confidence weighting policy for sentiment risk-pressure decisions.

    This creates a final confidence value for ranking and UI visibility. It does
    not place trades and does not override the hard gate. Execution/pre-trade
    layers must explicitly consume the output in a later Phase 9 slice.
    """

    decision: SentimentGateDecision
    model_confidence: float
    aligned_multiplier: float = 1.05
    macro_pressure_multiplier: float = 0.90
    extreme_macro_pressure_multiplier: float = 0.80
    weak_coverage_multiplier: float = 0.90
    missing_sentiment_multiplier: float = 0.90
    neutral_multiplier: float = 1.0
    minimum_confidence: float = 0.0
    maximum_confidence: float = 0.95


@dataclass(frozen=True, slots=True)
class SentimentConfidenceResult:
    """Weighted confidence result after applying macro sentiment pressure."""

    final_confidence: float
    confidence_multiplier: float
    confidence_delta: float


def evaluate_sentiment_gate(gate_input: SentimentGateInput) -> SentimentGateDecision:
    """Evaluate macro sentiment as a risk-pressure layer, not a universal gate."""

    _validate_gate_input(gate_input)

    sentiment = gate_input.news_sentiment_1d
    if sentiment is None:
        return SentimentGateDecision(
            state="downgraded",
            allowed=True,
            sentiment_bias="unknown",
            risk_flag="missing_sentiment",
            reason=(
                "No same-day or prior macro sentiment is available; "
                "allow but downgrade confidence."
            ),
        )

    sentiment_bias = classify_sentiment_bias(
        sentiment,
        bearish_threshold=gate_input.bearish_pressure_threshold,
        bullish_threshold=gate_input.bullish_pressure_threshold,
    )

    if gate_input.article_count_7d < gate_input.min_article_count_7d:
        return SentimentGateDecision(
            state="downgraded",
            allowed=True,
            sentiment_bias=sentiment_bias,
            risk_flag="weak_coverage",
            reason="Macro sentiment coverage is below the minimum article-count threshold.",
        )

    if _is_conflicting(gate_input.direction, sentiment_bias):
        return _evaluate_macro_conflict(gate_input, sentiment, sentiment_bias)

    if _is_aligned(gate_input.direction, sentiment_bias):
        return SentimentGateDecision(
            state="allowed",
            allowed=True,
            sentiment_bias=sentiment_bias,
            risk_flag="aligned",
            reason="Trade direction is aligned with crypto macro sentiment.",
        )

    return SentimentGateDecision(
        state="allowed",
        allowed=True,
        sentiment_bias=sentiment_bias,
        risk_flag="neutral",
        reason="Crypto macro sentiment is neutral or non-conflicting.",
    )


def calculate_position_multiplier(sizing_input: SentimentSizingInput) -> float:
    """Convert a sentiment gate decision into a bounded position-size multiplier.

    The multiplier is intentionally conservative. Macro pressure reduces size,
    weak coverage reduces trust, and blocked candidates receive zero exposure.
    """

    _validate_sizing_input(sizing_input)

    decision = sizing_input.decision
    if not decision.allowed or decision.state == "blocked":
        return 0.0

    if decision.risk_flag == "aligned":
        multiplier = sizing_input.aligned_multiplier
    elif decision.risk_flag == "macro_pressure":
        multiplier = sizing_input.macro_pressure_multiplier
    elif decision.risk_flag == "extreme_macro_pressure":
        multiplier = sizing_input.extreme_macro_pressure_multiplier
    elif decision.risk_flag == "weak_coverage":
        multiplier = sizing_input.weak_coverage_multiplier
    elif decision.risk_flag == "missing_sentiment":
        multiplier = sizing_input.missing_sentiment_multiplier
    elif decision.risk_flag == "neutral":
        multiplier = sizing_input.neutral_multiplier
    else:
        multiplier = sizing_input.base_multiplier

    return _clamp_multiplier(
        multiplier,
        minimum=sizing_input.minimum_multiplier,
        maximum=sizing_input.maximum_multiplier,
    )


def compute_sentiment_confidence(
    confidence_input: SentimentConfidenceInput,
) -> SentimentConfidenceResult:
    """Blend ML confidence with crypto macro sentiment pressure.

    The model remains the directional source of truth. Sentiment only nudges
    confidence up or down after the gate decision is known. Blocked candidates
    receive a final confidence of zero so they cannot rank as tradable.
    """

    _validate_confidence_input(confidence_input)

    decision = confidence_input.decision
    if not decision.allowed or decision.state == "blocked":
        final_confidence = 0.0
        return SentimentConfidenceResult(
            final_confidence=final_confidence,
            confidence_multiplier=0.0,
            confidence_delta=round(
                final_confidence - confidence_input.model_confidence,
                6,
            ),
        )

    multiplier = _confidence_multiplier_for_decision(confidence_input)
    final_confidence = _clamp_multiplier(
        confidence_input.model_confidence * multiplier,
        minimum=confidence_input.minimum_confidence,
        maximum=confidence_input.maximum_confidence,
    )
    return SentimentConfidenceResult(
        final_confidence=final_confidence,
        confidence_multiplier=multiplier,
        confidence_delta=round(final_confidence - confidence_input.model_confidence, 6),
    )

def classify_sentiment_bias(
    sentiment: float | None,
    *,
    bearish_threshold: float = -0.30,
    bullish_threshold: float = 0.30,
) -> SentimentBias:
    """Classify a normalized sentiment score into a compact directional bias."""

    if sentiment is None:
        return "unknown"
    if sentiment <= bearish_threshold:
        return "bearish"
    if sentiment >= bullish_threshold:
        return "bullish"
    return "neutral"


def calculate_intraday_sentiment_change(
    current_sentiment: float | None,
    morning_sentiment: float | None,
) -> float | None:
    """Calculate the structured intraday sentiment shift."""

    if current_sentiment is None or morning_sentiment is None:
        return None
    _validate_normalized_sentiment(current_sentiment, field_name="current_sentiment")
    _validate_normalized_sentiment(morning_sentiment, field_name="morning_sentiment")
    return round(current_sentiment - morning_sentiment, 6)


def _evaluate_macro_conflict(
    gate_input: SentimentGateInput,
    sentiment: float,
    sentiment_bias: SentimentBias,
) -> SentimentGateDecision:
    is_extreme = _is_extreme_macro_pressure(gate_input.direction, sentiment, gate_input)
    confidence = gate_input.model_confidence

    if (
        is_extreme
        and confidence is not None
        and confidence < gate_input.moderate_confidence_threshold
    ):
        return SentimentGateDecision(
            state="blocked",
            allowed=False,
            sentiment_bias=sentiment_bias,
            risk_flag="extreme_macro_pressure",
            reason=(
                "Extreme BTC/ETH macro sentiment conflicts with a weak "
                "or moderate setup."
            ),
        )

    if (
        not is_extreme
        and confidence is not None
        and confidence < gate_input.weak_confidence_threshold
    ):
        return SentimentGateDecision(
            state="blocked",
            allowed=False,
            sentiment_bias=sentiment_bias,
            risk_flag="macro_pressure",
            reason="BTC/ETH macro sentiment conflicts with a weak setup.",
        )

    if is_extreme:
        return SentimentGateDecision(
            state="downgraded",
            allowed=True,
            sentiment_bias=sentiment_bias,
            risk_flag="extreme_macro_pressure",
            reason=(
                "Extreme BTC/ETH macro sentiment conflicts with the trade; "
                "allow only as a high-risk setup."
            ),
        )

    return SentimentGateDecision(
        state="downgraded",
        allowed=True,
        sentiment_bias=sentiment_bias,
        risk_flag="macro_pressure",
        reason=(
            "BTC/ETH macro sentiment conflicts with the trade; "
            "downgrade instead of universally blocking."
        ),
    )


def _is_aligned(direction: TradeDirection, sentiment_bias: SentimentBias) -> bool:
    return (direction == "long" and sentiment_bias == "bullish") or (
        direction == "short" and sentiment_bias == "bearish"
    )


def _is_conflicting(direction: TradeDirection, sentiment_bias: SentimentBias) -> bool:
    return (direction == "long" and sentiment_bias == "bearish") or (
        direction == "short" and sentiment_bias == "bullish"
    )


def _is_extreme_macro_pressure(
    direction: TradeDirection,
    sentiment: float,
    gate_input: SentimentGateInput,
) -> bool:
    if direction == "long":
        return sentiment <= gate_input.bearish_extreme_threshold
    return sentiment >= gate_input.bullish_extreme_threshold


def _validate_gate_input(gate_input: SentimentGateInput) -> None:
    if gate_input.direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    if gate_input.news_sentiment_1d is not None:
        _validate_normalized_sentiment(
            gate_input.news_sentiment_1d,
            field_name="news_sentiment_1d",
        )
    if gate_input.model_confidence is not None:
        _validate_confidence(gate_input.model_confidence, field_name="model_confidence")
    if gate_input.article_count_7d < 0:
        raise ValueError("article_count_7d cannot be negative")
    if gate_input.min_article_count_7d < 0:
        raise ValueError("min_article_count_7d cannot be negative")
    if gate_input.bearish_extreme_threshold > gate_input.bearish_pressure_threshold:
        raise ValueError(
            "bearish_extreme_threshold must be at or below bearish_pressure_threshold"
        )
    if gate_input.bullish_extreme_threshold < gate_input.bullish_pressure_threshold:
        raise ValueError(
            "bullish_extreme_threshold must be at or above bullish_pressure_threshold"
        )
    if gate_input.bearish_pressure_threshold >= gate_input.bullish_pressure_threshold:
        raise ValueError(
            "bearish_pressure_threshold must be lower than bullish_pressure_threshold"
        )
    if gate_input.weak_confidence_threshold > gate_input.moderate_confidence_threshold:
        raise ValueError(
            "weak_confidence_threshold cannot exceed moderate_confidence_threshold"
        )


def _validate_sizing_input(sizing_input: SentimentSizingInput) -> None:
    multipliers = {
        "base_multiplier": sizing_input.base_multiplier,
        "aligned_multiplier": sizing_input.aligned_multiplier,
        "macro_pressure_multiplier": sizing_input.macro_pressure_multiplier,
        "extreme_macro_pressure_multiplier": (
            sizing_input.extreme_macro_pressure_multiplier
        ),
        "weak_coverage_multiplier": sizing_input.weak_coverage_multiplier,
        "missing_sentiment_multiplier": sizing_input.missing_sentiment_multiplier,
        "neutral_multiplier": sizing_input.neutral_multiplier,
        "minimum_multiplier": sizing_input.minimum_multiplier,
        "maximum_multiplier": sizing_input.maximum_multiplier,
    }
    for field_name, value in multipliers.items():
        if value < 0.0:
            raise ValueError(f"{field_name} cannot be negative")
    if sizing_input.minimum_multiplier > sizing_input.maximum_multiplier:
        raise ValueError("minimum_multiplier cannot exceed maximum_multiplier")


def _confidence_multiplier_for_decision(
    confidence_input: SentimentConfidenceInput,
) -> float:
    decision = confidence_input.decision
    if decision.risk_flag == "aligned":
        return confidence_input.aligned_multiplier
    if decision.risk_flag == "macro_pressure":
        return confidence_input.macro_pressure_multiplier
    if decision.risk_flag == "extreme_macro_pressure":
        return confidence_input.extreme_macro_pressure_multiplier
    if decision.risk_flag == "weak_coverage":
        return confidence_input.weak_coverage_multiplier
    if decision.risk_flag == "missing_sentiment":
        return confidence_input.missing_sentiment_multiplier
    if decision.risk_flag == "neutral":
        return confidence_input.neutral_multiplier
    return 1.0


def _validate_confidence_input(
    confidence_input: SentimentConfidenceInput,
) -> None:
    _validate_confidence(
        confidence_input.model_confidence,
        field_name="model_confidence",
    )
    multipliers = {
        "aligned_multiplier": confidence_input.aligned_multiplier,
        "macro_pressure_multiplier": confidence_input.macro_pressure_multiplier,
        "extreme_macro_pressure_multiplier": (
            confidence_input.extreme_macro_pressure_multiplier
        ),
        "weak_coverage_multiplier": confidence_input.weak_coverage_multiplier,
        "missing_sentiment_multiplier": confidence_input.missing_sentiment_multiplier,
        "neutral_multiplier": confidence_input.neutral_multiplier,
    }
    for field_name, value in multipliers.items():
        if value < 0.0:
            raise ValueError(f"{field_name} cannot be negative")
    if confidence_input.minimum_confidence > confidence_input.maximum_confidence:
        raise ValueError("minimum_confidence cannot exceed maximum_confidence")
    _validate_confidence(
        confidence_input.minimum_confidence,
        field_name="minimum_confidence",
    )
    _validate_confidence(
        confidence_input.maximum_confidence,
        field_name="maximum_confidence",
    )

def _validate_normalized_sentiment(value: float, *, field_name: str) -> None:
    if not -1.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be normalized between -1.0 and 1.0")


def _validate_confidence(value: float, *, field_name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")


def _clamp_multiplier(value: float, *, minimum: float, maximum: float) -> float:
    return round(min(max(value, minimum), maximum), 6)
