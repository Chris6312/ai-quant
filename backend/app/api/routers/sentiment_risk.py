"""Manual verification endpoints for the Phase 9 sentiment risk layer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.risk.pre_trade import PreTradeSentimentDecision, enforce_sentiment_pre_trade
from app.risk.sentiment_risk import (
    SentimentGateDecision,
    SentimentGateInput,
    SentimentSizingInput,
    calculate_position_multiplier,
    evaluate_sentiment_gate,
)

router = APIRouter(prefix="/risk/sentiment", tags=["risk"])


@router.get("/verify")
def verify_sentiment_risk_layer() -> dict[str, Any]:
    """Return deterministic manual checks for Phase 9 sentiment enforcement."""

    scenarios = [
        _crypto_scenario(
            name="bearish_macro_strong_long",
            description=(
                "Bearish BTC/ETH macro pressure downgrades a strong crypto long "
                "instead of universally blocking it."
            ),
            gate_input=SentimentGateInput(
                direction="long",
                news_sentiment_1d=-0.45,
                article_count_7d=8,
                model_confidence=0.72,
            ),
            requested_size=100.0,
        ),
        _crypto_scenario(
            name="bearish_macro_weak_long",
            description="Bearish BTC/ETH macro pressure blocks a weak crypto long.",
            gate_input=SentimentGateInput(
                direction="long",
                news_sentiment_1d=-0.45,
                article_count_7d=8,
                model_confidence=0.52,
            ),
            requested_size=100.0,
        ),
        _crypto_scenario(
            name="extreme_bearish_macro_high_confidence_long",
            description=(
                "Extreme bearish BTC/ETH macro pressure allows only a high-risk, "
                "high-confidence crypto long with reduced size."
            ),
            gate_input=SentimentGateInput(
                direction="long",
                news_sentiment_1d=-0.74,
                article_count_7d=9,
                model_confidence=0.78,
            ),
            requested_size=100.0,
        ),
        _crypto_scenario(
            name="bullish_macro_aligned_long",
            description="Bullish BTC/ETH macro sentiment allows an aligned crypto long.",
            gate_input=SentimentGateInput(
                direction="long",
                news_sentiment_1d=0.43,
                article_count_7d=10,
                model_confidence=0.62,
            ),
            requested_size=100.0,
        ),
        _stock_unscoped_scenario(),
    ]

    return {
        "phase": "Phase 9",
        "slice": "Slice 8",
        "status": "pass" if all(item["passed"] for item in scenarios) else "fail",
        "principle": "Macro sentiment is a risk-pressure layer, not a universal gate.",
        "macro_scope": "BTC + ETH sentiment flows into crypto as macro pressure only.",
        "scenarios": scenarios,
    }


def _crypto_scenario(
    *,
    name: str,
    description: str,
    gate_input: SentimentGateInput,
    requested_size: float,
) -> dict[str, Any]:
    decision = evaluate_sentiment_gate(gate_input)
    position_multiplier = calculate_position_multiplier(
        SentimentSizingInput(decision=decision)
    )
    sentiment_gate_payload = _sentiment_gate_payload(decision, position_multiplier)
    pre_trade = _evaluate_pre_trade(
        requested_size=requested_size,
        sentiment_gate_payload=sentiment_gate_payload,
    )

    return {
        "name": name,
        "description": description,
        "passed": _scenario_passed(decision, pre_trade),
        "gate": sentiment_gate_payload,
        "pre_trade": _pre_trade_payload(pre_trade),
    }


def _stock_unscoped_scenario() -> dict[str, Any]:
    pre_trade = enforce_sentiment_pre_trade(
        symbol="AAPL",
        asset_class="stock",
        side="buy",
        requested_size=100.0,
        sentiment_gate={
            "state": "blocked",
            "allowed": False,
            "position_multiplier": 0.0,
        },
    )
    return {
        "name": "stock_unscoped_from_crypto_macro_sentiment",
        "description": "Stocks remain outside the BTC/ETH crypto macro sentiment scope.",
        "passed": pre_trade.allowed and pre_trade.state == "unscoped",
        "gate": {
            "state": "blocked",
            "allowed": False,
            "position_multiplier": 0.0,
        },
        "pre_trade": _pre_trade_payload(pre_trade),
    }


def _evaluate_pre_trade(
    *,
    requested_size: float,
    sentiment_gate_payload: dict[str, Any],
) -> PreTradeSentimentDecision:
    return enforce_sentiment_pre_trade(
        symbol="BTC/USD",
        asset_class="crypto",
        side="buy",
        requested_size=requested_size,
        sentiment_gate=sentiment_gate_payload,
    )


def _sentiment_gate_payload(
    decision: SentimentGateDecision,
    position_multiplier: float,
) -> dict[str, Any]:
    return {
        "state": decision.state,
        "allowed": decision.allowed,
        "sentiment_bias": decision.sentiment_bias,
        "risk_flag": decision.risk_flag,
        "reason": decision.reason,
        "position_multiplier": position_multiplier,
    }


def _pre_trade_payload(decision: PreTradeSentimentDecision) -> dict[str, Any]:
    return {
        "state": decision.state,
        "allowed": decision.allowed,
        "original_size": decision.original_size,
        "adjusted_size": decision.adjusted_size,
        "position_multiplier": decision.position_multiplier,
        "final_confidence": decision.final_confidence,
        "reason": decision.reason,
    }


def _scenario_passed(
    decision: SentimentGateDecision,
    pre_trade: PreTradeSentimentDecision,
) -> bool:
    if not decision.allowed:
        return not pre_trade.allowed and pre_trade.state == "blocked"
    if decision.state == "downgraded":
        return pre_trade.allowed and pre_trade.state in {"scaled", "allowed"}
    return pre_trade.allowed
