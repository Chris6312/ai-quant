"""Tests for Phase 5 feature contract and parity checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import inf

import pytest

from app.ml.features import (
    ALL_FEATURES,
    RESEARCH_FEATURES,
    FeatureEngineer,
    ResearchInputs,
    build_feature_contract_summary,
    ordered_feature_row,
    validate_feature_vector,
)
from app.models.domain import Candle


def _build_history(symbol: str, asset_class: str, count: int = 220) -> list[Candle]:
    """Return a deterministic candle history for feature tests."""

    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(count):
        base_price = 100.0 + (index * 0.75)
        open_price = base_price + ((index % 3) * 0.1)
        close_price = base_price + ((index % 5) * 0.2)
        high_price = close_price + 0.8
        low_price = open_price - 0.7
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol=symbol,
                asset_class=asset_class,
                timeframe="1Day",
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=1_000.0 + (index * 10.0),
                source="unit_test",
            )
        )
    return candles


def test_feature_engineer_returns_full_contract_for_stock_and_crypto() -> None:
    """Stock and crypto should emit the same feature keys in the same contract."""

    engineer = FeatureEngineer()
    stock_history = _build_history("AAPL", "stock")
    crypto_history = _build_history("BTC/USD", "crypto")
    research = ResearchInputs(
        news_sentiment_1d=0.8,
        news_sentiment_7d=0.6,
        news_article_count_7d=12,
        congress_buy_score=0.4,
        insider_buy_score=0.7,
        analyst_upgrade_score=0.5,
        watchlist_research_score=88.0,
    )

    stock_features = engineer.build(stock_history, "stock", research)
    crypto_features = engineer.build(crypto_history, "crypto", research)
    crypto_default_features = engineer.build(crypto_history, "crypto", None)

    assert stock_features is not None
    assert crypto_features is not None
    assert crypto_default_features is not None
    assert list(stock_features) == ALL_FEATURES
    assert list(crypto_features) == ALL_FEATURES
    assert tuple(stock_features) == tuple(crypto_features)
    assert all(
        crypto_features[name] == crypto_default_features[name] for name in RESEARCH_FEATURES
    )
    assert stock_features["news_sentiment_1d"] == pytest.approx(0.8)
    assert stock_features["watchlist_research_score"] == pytest.approx(88.0)


def test_feature_engineer_is_reproducible_for_identical_inputs() -> None:
    """Feature generation should be deterministic for the same source history."""

    engineer = FeatureEngineer()
    history = _build_history("MSFT", "stock")
    research = ResearchInputs(news_sentiment_7d=0.25, insider_value_60d=500_000.0)

    first = engineer.build(history, "stock", research)
    second = engineer.build(history, "stock", research)

    assert first is not None
    assert second is not None
    assert first == second
    assert ordered_feature_row(first) == ordered_feature_row(second)


def test_validate_feature_vector_flags_contract_problems() -> None:
    """The contract validator should expose missing, extra, and non-finite fields."""

    features = dict.fromkeys(ALL_FEATURES, 1.0)
    features.pop("macd")
    features["unexpected_feature"] = 3.0
    features["rsi_14"] = inf

    validation = validate_feature_vector(features)

    assert validation.missing == ("macd",)
    assert validation.extra == ("unexpected_feature",)
    assert validation.nonfinite == ("rsi_14",)

    with pytest.raises(ValueError, match="Feature vector does not match ML contract"):
        ordered_feature_row(features)


def test_feature_contract_summary_matches_feature_lists() -> None:
    """The summary endpoint payload should match the canonical contract."""

    summary = build_feature_contract_summary()

    assert summary["feature_count"] == len(ALL_FEATURES)
    assert summary["technical_feature_count"] + summary["research_feature_count"] == len(
        ALL_FEATURES
    )
    assert summary["all_features"] == ALL_FEATURES
    assert summary["research_features"] == RESEARCH_FEATURES
