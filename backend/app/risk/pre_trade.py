"""Pre-trade enforcement for sentiment-aware crypto execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

PreTradeState = Literal["allowed", "blocked", "scaled", "unscoped"]


@dataclass(frozen=True, slots=True)
class PreTradeSentimentDecision:
    """Execution-layer decision produced from a serialized sentiment gate payload."""

    state: PreTradeState
    allowed: bool
    original_size: float
    adjusted_size: float
    position_multiplier: float
    final_confidence: float | None
    reason: str


def enforce_sentiment_pre_trade(
    *,
    symbol: str,
    asset_class: str,
    side: str,
    requested_size: float,
    sentiment_gate: Mapping[str, object] | None,
) -> PreTradeSentimentDecision:
    """Apply serialized sentiment risk controls immediately before order submission."""

    _validate_requested_size(requested_size)

    if asset_class != "crypto" or side != "buy":
        return PreTradeSentimentDecision(
            state="unscoped",
            allowed=True,
            original_size=requested_size,
            adjusted_size=requested_size,
            position_multiplier=1.0,
            final_confidence=None,
            reason="Sentiment pre-trade enforcement is scoped to crypto buys only.",
        )

    if sentiment_gate is None:
        return PreTradeSentimentDecision(
            state="allowed",
            allowed=True,
            original_size=requested_size,
            adjusted_size=requested_size,
            position_multiplier=1.0,
            final_confidence=None,
            reason=(
                f"No sentiment gate payload was provided for {symbol}; "
                "allow without sentiment sizing."
            ),
        )

    allowed = _coerce_bool(sentiment_gate.get("allowed"))
    state = str(sentiment_gate.get("state") or "").lower()
    multiplier = _coerce_multiplier(sentiment_gate.get("position_multiplier"))
    final_confidence = _coerce_optional_float(sentiment_gate.get("final_confidence"))

    if not allowed or state == "blocked" or multiplier <= 0.0:
        return PreTradeSentimentDecision(
            state="blocked",
            allowed=False,
            original_size=requested_size,
            adjusted_size=0.0,
            position_multiplier=0.0,
            final_confidence=final_confidence,
            reason="Sentiment gate blocked the crypto trade before execution.",
        )

    adjusted_size = round(requested_size * multiplier, 8)
    if adjusted_size <= 0.0:
        return PreTradeSentimentDecision(
            state="blocked",
            allowed=False,
            original_size=requested_size,
            adjusted_size=0.0,
            position_multiplier=0.0,
            final_confidence=final_confidence,
            reason="Sentiment sizing reduced the crypto order to zero.",
        )

    if multiplier != 1.0:
        return PreTradeSentimentDecision(
            state="scaled",
            allowed=True,
            original_size=requested_size,
            adjusted_size=adjusted_size,
            position_multiplier=multiplier,
            final_confidence=final_confidence,
            reason="Sentiment risk pressure adjusted crypto order size before execution.",
        )

    return PreTradeSentimentDecision(
        state="allowed",
        allowed=True,
        original_size=requested_size,
        adjusted_size=adjusted_size,
        position_multiplier=multiplier,
        final_confidence=final_confidence,
        reason="Sentiment gate allowed the crypto trade without size adjustment.",
    )


def _validate_requested_size(requested_size: float) -> None:
    if requested_size <= 0.0:
        raise ValueError("requested_size must be greater than zero")


def _coerce_bool(value: object) -> bool:
    return value is True


def _coerce_multiplier(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 1.0
    if isinstance(value, int | float):
        multiplier = float(value)
        if multiplier < 0.0:
            raise ValueError("position_multiplier cannot be negative")
        return round(multiplier, 6)
    raise ValueError("position_multiplier must be numeric when provided")


def _coerce_optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None