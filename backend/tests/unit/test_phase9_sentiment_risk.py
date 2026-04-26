"""Phase 9 sentiment risk-pressure tests."""

from __future__ import annotations

import pytest

from app.api.routers.ml import (
    _prediction_action_after_sentiment_gate,
    _prediction_signal_event,
    _sentiment_gate_api_payload,
    _sentiment_gate_for_prediction,
)
from app.risk.sentiment_risk import (
    SentimentConfidenceInput,
    SentimentGateInput,
    SentimentSizingInput,
    calculate_intraday_sentiment_change,
    calculate_position_multiplier,
    classify_sentiment_bias,
    compute_sentiment_confidence,
    evaluate_sentiment_gate,
)
from app.tasks.worker import celery_app


def test_celery_beat_schedules_crypto_news_every_four_hours() -> None:
    """Crypto sentiment should refresh on a structured 24/7 cadence."""

    schedule = celery_app.conf.beat_schedule
    refresh = schedule["news-sentiment-crypto-refresh"]

    assert refresh["task"] == "tasks.news_sentiment.daily_crypto_sync"
    assert refresh["schedule"].hour == {2, 6, 10, 14, 18, 22}
    assert refresh["schedule"].minute == {30}


def test_celery_beat_preserves_ml_daily_timing() -> None:
    """The crypto sentiment refresh should not move ML candle or prediction jobs."""

    schedule = celery_app.conf.beat_schedule

    assert schedule["ml-daily-candle-sync"]["schedule"].hour == {8}
    assert schedule["ml-daily-candle-sync"]["schedule"].minute == {40}
    assert schedule["ml-prediction-snapshot"]["schedule"].hour == {8}
    assert schedule["ml-prediction-snapshot"]["schedule"].minute == {55}


def test_bearish_macro_pressure_downgrades_strong_long_instead_of_blocking() -> None:
    """BTC/ETH bearish pressure is not a universal hard gate for crypto longs."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.45,
            article_count_7d=7,
            model_confidence=0.72,
        )
    )

    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.sentiment_bias == "bearish"
    assert decision.risk_flag == "macro_pressure"
    assert decision.reason == (
        "BTC/ETH macro sentiment conflicts with the trade; "
        "downgrade instead of universally blocking."
    )


def test_bearish_macro_pressure_blocks_weak_long() -> None:
    """BTC/ETH bearish pressure should block weak long setups."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.45,
            article_count_7d=7,
            model_confidence=0.52,
        )
    )

    assert decision.allowed is False
    assert decision.state == "blocked"
    assert decision.sentiment_bias == "bearish"
    assert decision.risk_flag == "macro_pressure"
    assert decision.reason == "BTC/ETH macro sentiment conflicts with a weak setup."


def test_extreme_bearish_macro_blocks_moderate_long() -> None:
    """Extreme BTC/ETH macro pressure should block weak or moderate longs."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.74,
            article_count_7d=9,
            model_confidence=0.61,
        )
    )

    assert decision.allowed is False
    assert decision.state == "blocked"
    assert decision.sentiment_bias == "bearish"
    assert decision.risk_flag == "extreme_macro_pressure"
    assert decision.reason == (
        "Extreme BTC/ETH macro sentiment conflicts with a weak or moderate setup."
    )


def test_extreme_bearish_macro_allows_high_confidence_long_with_warning() -> None:
    """Very strong setups can survive extreme macro pressure, but only downgraded."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.74,
            article_count_7d=9,
            model_confidence=0.78,
        )
    )

    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.sentiment_bias == "bearish"
    assert decision.risk_flag == "extreme_macro_pressure"
    assert decision.reason == (
        "Extreme BTC/ETH macro sentiment conflicts with the trade; "
        "allow only as a high-risk setup."
    )


def test_bullish_macro_pressure_downgrades_strong_short_instead_of_blocking() -> None:
    """The pressure-layer rule is symmetrical for short candidates."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="short",
            news_sentiment_1d=0.42,
            article_count_7d=6,
            model_confidence=0.71,
        )
    )

    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.sentiment_bias == "bullish"
    assert decision.risk_flag == "macro_pressure"


def test_sentiment_allows_aligned_long_trade() -> None:
    """Strong bullish sentiment should allow an aligned long candidate."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.41,
            article_count_7d=8,
            model_confidence=0.60,
        )
    )

    assert decision.allowed is True
    assert decision.state == "allowed"
    assert decision.sentiment_bias == "bullish"
    assert decision.risk_flag == "aligned"
    assert decision.reason == "Trade direction is aligned with crypto macro sentiment."


def test_low_article_count_downgrades_instead_of_blocking() -> None:
    """Weak coverage should reduce trust without blocking the trade candidate."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.80,
            article_count_7d=1,
            model_confidence=0.40,
            min_article_count_7d=3,
        )
    )

    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.sentiment_bias == "bearish"
    assert decision.risk_flag == "weak_coverage"


def test_missing_sentiment_downgrades_without_blocking() -> None:
    """Missing sentiment should fail soft until the pre-trade layer consumes confidence."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=None,
            article_count_7d=0,
            model_confidence=0.50,
        )
    )

    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.sentiment_bias == "unknown"
    assert decision.risk_flag == "missing_sentiment"


def test_neutral_sentiment_allows_without_alignment_flag() -> None:
    """Neutral sentiment should not masquerade as alignment."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.05,
            article_count_7d=4,
            model_confidence=0.56,
        )
    )

    assert decision.allowed is True
    assert decision.state == "allowed"
    assert decision.sentiment_bias == "neutral"
    assert decision.risk_flag == "neutral"


def test_sentiment_bias_classification_uses_threshold_edges() -> None:
    """Threshold edges are inclusive so boundary signals are deterministic."""

    assert classify_sentiment_bias(-0.30) == "bearish"
    assert classify_sentiment_bias(0.30) == "bullish"
    assert classify_sentiment_bias(0.0) == "neutral"
    assert classify_sentiment_bias(None) == "unknown"


def test_intraday_sentiment_change_detects_narrative_shift() -> None:
    """Intraday change should compare current sentiment against the morning baseline."""

    assert calculate_intraday_sentiment_change(0.45, -0.15) == 0.6


def test_intraday_sentiment_change_requires_both_timestamps() -> None:
    """Missing current or morning sentiment should not become a fake zero signal."""

    assert calculate_intraday_sentiment_change(None, -0.15) is None
    assert calculate_intraday_sentiment_change(0.45, None) is None


def test_intraday_sentiment_change_rejects_out_of_range_sentiment() -> None:
    """Intraday sentiment inputs must stay normalized before risk use."""

    with pytest.raises(ValueError, match="current_sentiment"):
        calculate_intraday_sentiment_change(1.20, 0.10)


def test_sentiment_gate_rejects_out_of_range_sentiment() -> None:
    """Sentiment scores must be normalized before risk gating."""

    with pytest.raises(ValueError, match="news_sentiment_1d"):
        evaluate_sentiment_gate(
            SentimentGateInput(
                direction="long",
                news_sentiment_1d=1.5,
                article_count_7d=4,
            )
        )


def test_sentiment_gate_rejects_out_of_range_confidence() -> None:
    """Model confidence must be normalized before risk gating."""

    with pytest.raises(ValueError, match="model_confidence"):
        evaluate_sentiment_gate(
            SentimentGateInput(
                direction="long",
                news_sentiment_1d=-0.40,
                article_count_7d=4,
                model_confidence=1.5,
            )
        )



def test_position_multiplier_zeroes_blocked_candidates() -> None:
    """Blocked sentiment decisions should receive no position exposure."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.55,
            article_count_7d=8,
            model_confidence=0.50,
        )
    )

    assert calculate_position_multiplier(SentimentSizingInput(decision=decision)) == 0.0


def test_position_multiplier_reduces_macro_pressure() -> None:
    """Macro pressure should reduce, not erase, otherwise strong candidates."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.45,
            article_count_7d=8,
            model_confidence=0.72,
        )
    )

    assert calculate_position_multiplier(SentimentSizingInput(decision=decision)) == 0.75


def test_position_multiplier_reduces_extreme_macro_pressure_more() -> None:
    """Extreme pressure should shrink size more than normal macro pressure."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.74,
            article_count_7d=8,
            model_confidence=0.78,
        )
    )

    assert calculate_position_multiplier(SentimentSizingInput(decision=decision)) == 0.5


def test_position_multiplier_boosts_aligned_sentiment_conservatively() -> None:
    """Aligned macro sentiment can receive a bounded sizing boost."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.44,
            article_count_7d=8,
            model_confidence=0.62,
        )
    )

    assert calculate_position_multiplier(SentimentSizingInput(decision=decision)) == 1.1


def test_position_multiplier_reduces_weak_coverage_and_missing_sentiment() -> None:
    """Weak coverage and missing sentiment should fail soft with smaller size."""

    weak_coverage = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.50,
            article_count_7d=1,
            model_confidence=0.70,
        )
    )
    missing = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=None,
            article_count_7d=0,
            model_confidence=0.70,
        )
    )

    assert calculate_position_multiplier(SentimentSizingInput(decision=weak_coverage)) == 0.75
    assert calculate_position_multiplier(SentimentSizingInput(decision=missing)) == 0.75


def test_position_multiplier_clamps_custom_boosts() -> None:
    """Custom policy multipliers should stay inside configured safety bounds."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.44,
            article_count_7d=8,
            model_confidence=0.62,
        )
    )

    assert (
        calculate_position_multiplier(
            SentimentSizingInput(
                decision=decision,
                aligned_multiplier=2.0,
                maximum_multiplier=1.25,
            )
        )
        == 1.25
    )


def test_position_multiplier_rejects_negative_policy_values() -> None:
    """Sizing policy values should never become negative risk exposure."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.44,
            article_count_7d=8,
            model_confidence=0.62,
        )
    )

    with pytest.raises(ValueError, match="macro_pressure_multiplier"):
        calculate_position_multiplier(
            SentimentSizingInput(
                decision=decision,
                macro_pressure_multiplier=-0.25,
            )
        )



def test_confidence_weighting_zeroes_blocked_candidates() -> None:
    """Blocked sentiment decisions should not rank as tradable confidence."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.55,
            article_count_7d=8,
            model_confidence=0.50,
        )
    )
    result = compute_sentiment_confidence(
        SentimentConfidenceInput(decision=decision, model_confidence=0.50)
    )

    assert result.final_confidence == 0.0
    assert result.confidence_multiplier == 0.0
    assert result.confidence_delta == -0.5


def test_confidence_weighting_reduces_macro_pressure() -> None:
    """Macro pressure should lower confidence without killing strong setups."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.45,
            article_count_7d=8,
            model_confidence=0.72,
        )
    )
    result = compute_sentiment_confidence(
        SentimentConfidenceInput(decision=decision, model_confidence=0.72)
    )

    assert result.final_confidence == 0.648
    assert result.confidence_multiplier == 0.9
    assert result.confidence_delta == -0.072


def test_confidence_weighting_reduces_extreme_macro_pressure_more() -> None:
    """Extreme pressure should reduce confidence more than normal pressure."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.74,
            article_count_7d=8,
            model_confidence=0.78,
        )
    )
    result = compute_sentiment_confidence(
        SentimentConfidenceInput(decision=decision, model_confidence=0.78)
    )

    assert result.final_confidence == 0.624
    assert result.confidence_multiplier == 0.8
    assert result.confidence_delta == -0.156


def test_confidence_weighting_boosts_aligned_signal_with_cap() -> None:
    """Aligned sentiment can boost confidence, but not beyond the safety cap."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.52,
            article_count_7d=8,
            model_confidence=0.92,
        )
    )
    result = compute_sentiment_confidence(
        SentimentConfidenceInput(decision=decision, model_confidence=0.92)
    )

    assert result.final_confidence == 0.95
    assert result.confidence_multiplier == 1.05
    assert result.confidence_delta == 0.03


def test_confidence_weighting_rejects_negative_policy_values() -> None:
    """Confidence policy multipliers should never become negative."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.52,
            article_count_7d=8,
            model_confidence=0.62,
        )
    )

    with pytest.raises(ValueError, match="macro_pressure_multiplier"):
        compute_sentiment_confidence(
            SentimentConfidenceInput(
                decision=decision,
                model_confidence=0.62,
                macro_pressure_multiplier=-0.10,
            )
        )

def test_crypto_prediction_sentiment_gate_downgrades_strong_conflicting_signal() -> None:
    """Strong crypto longs should stay signalable under bearish macro pressure."""

    decision = _sentiment_gate_for_prediction(
        "crypto",
        "long",
        {
            "news_sentiment_1d": -0.55,
            "news_article_count_7d": 8.0,
        },
        model_confidence=0.72,
    )

    assert decision is not None
    assert decision.allowed is True
    assert decision.state == "downgraded"
    assert decision.risk_flag == "macro_pressure"
    assert _prediction_action_after_sentiment_gate("signal", decision) == "signal"


def test_crypto_prediction_sentiment_gate_blocks_weak_conflicting_signal() -> None:
    """Weak crypto longs should be skipped when BTC/ETH macro pressure conflicts."""

    decision = _sentiment_gate_for_prediction(
        "crypto",
        "long",
        {
            "news_sentiment_1d": -0.55,
            "news_article_count_7d": 8.0,
        },
        model_confidence=0.51,
    )

    assert decision is not None
    assert decision.allowed is False
    assert decision.state == "blocked"
    assert decision.risk_flag == "macro_pressure"
    assert _prediction_action_after_sentiment_gate("signal", decision) == "skip"


def test_crypto_prediction_sentiment_gate_preserves_aligned_signal() -> None:
    """Aligned crypto sentiment should not suppress a valid ML signal."""

    decision = _sentiment_gate_for_prediction(
        "crypto",
        "long",
        {
            "news_sentiment_1d": 0.44,
            "news_article_count_7d": 9.0,
        },
        model_confidence=0.58,
    )

    assert decision is not None
    assert decision.allowed is True
    assert decision.risk_flag == "aligned"
    assert _prediction_action_after_sentiment_gate("signal", decision) == "signal"


def test_prediction_sentiment_gate_does_not_override_existing_skip() -> None:
    """Sentiment gating should never resurrect a candidate skipped by ML rules."""

    decision = _sentiment_gate_for_prediction(
        "crypto",
        "long",
        {
            "news_sentiment_1d": 0.62,
            "news_article_count_7d": 12.0,
        },
        model_confidence=0.72,
    )

    assert _prediction_action_after_sentiment_gate("skip", decision) == "skip"


def test_prediction_sentiment_gate_is_crypto_only_for_this_slice() -> None:
    """Stocks should stay out of the crypto sentiment gate until explicitly scoped."""

    assert (
        _sentiment_gate_for_prediction(
            "stock",
            "long",
            {
                "news_sentiment_1d": -0.80,
                "news_article_count_7d": 10.0,
            },
            model_confidence=0.40,
        )
        is None
    )



def test_sentiment_gate_payload_includes_weighted_confidence() -> None:
    """API payload should expose confidence weighting for UI and ranking visibility."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=-0.45,
            article_count_7d=8,
            model_confidence=0.72,
        )
    )

    assert _sentiment_gate_api_payload(decision, model_confidence=0.72) == {
        "state": "downgraded",
        "allowed": True,
        "sentiment_bias": "bearish",
        "risk_flag": "macro_pressure",
        "reason": (
            "BTC/ETH macro sentiment conflicts with the trade; "
            "downgrade instead of universally blocking."
        ),
        "position_multiplier": 0.75,
        "confidence_multiplier": 0.9,
        "final_confidence": 0.648,
        "confidence_delta": -0.072,
    }

def test_prediction_signal_event_carries_sentiment_gate_payload() -> None:
    """Signal events should include sentiment context for downstream debugging."""

    decision = evaluate_sentiment_gate(
        SentimentGateInput(
            direction="long",
            news_sentiment_1d=0.52,
            article_count_7d=6,
            model_confidence=0.72,
        )
    )
    event = _prediction_signal_event(
        {
            "action": "signal",
            "prediction_id": "crypto:BTC/USD:2026-04-26T00:00:00+00:00",
            "model_id": "crypto-138",
            "symbol": "BTC/USD",
            "asset_class": "crypto",
            "direction": "long",
            "confidence": 0.72,
            "candle_time": "2026-04-26T00:00:00+00:00",
            "sentiment_gate": _sentiment_gate_api_payload(decision),
        }
    )

    assert event is not None
    assert event["sentiment_gate"] == {
        "state": "allowed",
        "allowed": True,
        "sentiment_bias": "bullish",
        "risk_flag": "aligned",
        "reason": "Trade direction is aligned with crypto macro sentiment.",
        "position_multiplier": 1.1,
        "confidence_multiplier": None,
        "final_confidence": None,
        "confidence_delta": None,
    }