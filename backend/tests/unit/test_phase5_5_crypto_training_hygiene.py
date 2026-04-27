"""Tests for Phase 5.5 crypto ML training hygiene."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ml.features import (
    CRYPTO_EXCLUDED_CALENDAR_FEATURES,
    CRYPTO_FEATURES,
    CRYPTO_NOT_APPLICABLE_RESEARCH_FEATURES,
    CRYPTO_SOURCE_BACKED_RESEARCH_FEATURES,
    FeatureEngineer,
    feature_names_for_asset_class,
)
from app.ml.trainer import WalkForwardTrainer
from app.models.domain import Candle


def _candle(index: int, close: float, asset_class: str = "crypto") -> Candle:
    """Build a deterministic daily candle."""

    return Candle(
        time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        symbol="BTC/USD" if asset_class == "crypto" else "AAPL",
        asset_class=asset_class,
        timeframe="1Day",
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1_000.0,
        source="unit_test",
    )


def _history(asset_class: str = "crypto") -> list[Candle]:
    """Return enough candles to build full technical features."""

    return [_candle(index, 100.0 + index, asset_class) for index in range(220)]


def test_crypto_feature_contract_excludes_calendar_and_stock_only_features() -> None:
    """Crypto model input should not include calendar ghosts or stock-only zeros."""

    crypto_feature_names = feature_names_for_asset_class("crypto")

    assert crypto_feature_names == CRYPTO_FEATURES
    for feature_name in CRYPTO_EXCLUDED_CALENDAR_FEATURES:
        assert feature_name not in crypto_feature_names
    for feature_name in CRYPTO_NOT_APPLICABLE_RESEARCH_FEATURES:
        assert feature_name not in crypto_feature_names
    assert "watchlist_research_score" not in crypto_feature_names
    for feature_name in CRYPTO_SOURCE_BACKED_RESEARCH_FEATURES:
        assert feature_name in crypto_feature_names


def test_crypto_feature_engineer_emits_only_crypto_contract() -> None:
    """Crypto feature vectors should match the reduced crypto-only contract."""

    features = FeatureEngineer().build(_history("crypto"), "crypto")

    assert features is not None
    assert list(features) == CRYPTO_FEATURES


def test_crypto_label_threshold_uses_larger_daily_move_boundary() -> None:
    """A 0.5% crypto daily move is flat, while the stock threshold still labels it up."""

    trainer = WalkForwardTrainer()
    crypto_labels = trainer._label_candles(
        [_candle(0, 100.0, "crypto"), _candle(1, 100.5, "crypto")],
        "crypto",
    )
    stock_labels = trainer._label_candles(
        [_candle(0, 100.0, "stock"), _candle(1, 100.5, "stock")],
        "stock",
    )

    assert crypto_labels == [1, 1]
    assert stock_labels == [2, 1]
