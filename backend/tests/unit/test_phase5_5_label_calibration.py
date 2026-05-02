"""Tests for Slice 5.5.7 ML label calibration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from app.ml.labels import (
    TradeLabelConfig,
    build_long_trade_labels,
    label_balance_report,
)
from app.ml.trainer import TrainerConfig, WalkForwardTrainer, _TrainingSample
from app.models.domain import Candle


def _candle(
    index: int,
    close: float,
    *,
    low: float | None = None,
    high: float | None = None,
) -> Candle:
    """Build a deterministic crypto daily candle."""

    return Candle(
        time=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="1Day",
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1_000.0,
        source="unit_test",
    )


def test_long_trade_labels_use_first_profit_or_stop_barrier() -> None:
    """Triple-barrier labels should encode long trade outcomes only."""

    labels = build_long_trade_labels(
        [
            _candle(0, 100.0),
            _candle(1, 100.0, low=99.4, high=101.0),
            _candle(2, 100.0, low=98.0, high=100.2),
            _candle(3, 100.0),
        ],
        TradeLabelConfig(
            profit_target_pct=0.0075,
            stop_loss_pct=0.0075,
            max_holding_candles=1,
        ),
    )

    assert labels == [2, 0, 1, 1]


def test_class_balance_report_names_negative_crypto_as_block_long() -> None:
    """Negative crypto labels must be diagnostics for suppressing longs, not shorts."""

    report = label_balance_report([0, 1, 1, 2])

    assert report["counts"] == {0: 1, 1: 2, 2: 1}
    meanings = report["label_meanings"]
    assert meanings["0"] == "stop_hit_first_block_long"
    assert "short" not in meanings["0"]


def test_crypto_sample_weights_combine_class_balance_and_recency() -> None:
    """Recent rows should receive extra weight on top of class balance."""

    trainer = WalkForwardTrainer(
        TrainerConfig(
            recent_sample_weight_days=30,
            recent_sample_weight_multiplier=2.0,
        )
    )
    samples = [
        _TrainingSample(
            timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            month_key=(2025, 1),
            features={},
            label=0,
            next_return=0.0,
            symbol="BTC/USD",
        ),
        _TrainingSample(
            timestamp=datetime(2025, 3, 1, tzinfo=UTC),
            month_key=(2025, 3),
            features={},
            label=1,
            next_return=0.0,
            symbol="BTC/USD",
        ),
        _TrainingSample(
            timestamp=datetime(2025, 3, 2, tzinfo=UTC),
            month_key=(2025, 3),
            features={},
            label=2,
            next_return=0.0,
            symbol="BTC/USD",
        ),
    ]

    weights = trainer._sample_weights(np.asarray([0, 1, 2]), "crypto", samples)

    assert weights is not None
    assert weights.tolist() == [1.0, 2.0, 2.0]


def test_walk_forward_folds_purge_and_embargo_label_windows() -> None:
    """Train rows near validation should be removed when labels overlap the fold."""

    trainer = WalkForwardTrainer(
        TrainerConfig(
            train_months=1,
            test_months=1,
            trade_label_lookahead_candles=2,
        )
    )
    samples = [
        _TrainingSample(
            timestamp=datetime(2026, 1, 28, tzinfo=UTC),
            month_key=(2026, 1),
            features={},
            label=1,
            next_return=0.0,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 1, 30, tzinfo=UTC),
        ),
        _TrainingSample(
            timestamp=datetime(2026, 1, 29, tzinfo=UTC),
            month_key=(2026, 1),
            features={},
            label=1,
            next_return=0.0,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 1, 31, tzinfo=UTC),
        ),
        _TrainingSample(
            timestamp=datetime(2026, 1, 30, tzinfo=UTC),
            month_key=(2026, 1),
            features={},
            label=1,
            next_return=0.0,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 2, 1, tzinfo=UTC),
        ),
        _TrainingSample(
            timestamp=datetime(2026, 1, 31, tzinfo=UTC),
            month_key=(2026, 1),
            features={},
            label=1,
            next_return=0.0,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 2, 2, tzinfo=UTC),
        ),
        _TrainingSample(
            timestamp=datetime(2026, 2, 1, tzinfo=UTC),
            month_key=(2026, 2),
            features={},
            label=2,
            next_return=0.01,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 2, 3, tzinfo=UTC),
        ),
        _TrainingSample(
            timestamp=datetime(2026, 2, 2, tzinfo=UTC),
            month_key=(2026, 2),
            features={},
            label=0,
            next_return=-0.01,
            symbol="BTC/USD",
            label_window_end=datetime(2026, 2, 4, tzinfo=UTC),
        ),
    ]

    folds = trainer._build_folds(samples)

    assert len(folds) == 1
    train_samples, test_samples = folds[0]
    assert [sample.timestamp.day for sample in train_samples] == [28, 29]
    assert [sample.timestamp.day for sample in test_samples] == [1, 2]
