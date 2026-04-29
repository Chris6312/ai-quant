"""Slice 5.7 probability calibration diagnostics tests."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.ml.calibration import build_long_probability_calibration_report
from app.ml.trainer import WalkForwardTrainer, _TrainingSample
from app.models.domain import Candle


def test_calibration_buckets_measure_probability_separation() -> None:
    probabilities = np.asarray(
        [
            [0.35, 0.45, 0.20],
            [0.25, 0.30, 0.45],
            [0.15, 0.25, 0.60],
            [0.10, 0.20, 0.70],
            [0.05, 0.15, 0.80],
            [0.05, 0.10, 0.85],
        ],
        dtype=float,
    )
    labels = [0, 1, 2, 2, 2, 2]
    returns = [-0.02, 0.0, 0.01, 0.02, 0.03, 0.04]

    report = build_long_probability_calibration_report(
        probabilities,
        labels,
        returns,
        minimum_high_confidence_samples=1,
    )

    assert report["sample_count"] == 6
    assert report["bucket_count"] == 5
    assert report["high_confidence_count"] == 4
    assert report["high_confidence_win_rate"] == 1.0
    assert report["separation"] > 0.0
    assert report["usable_for_live_gate"] is True
    assert report["buckets"][2]["label"] == "0.50-0.60"


def test_calibration_marks_clustered_probabilities_research_only() -> None:
    probabilities = np.asarray(
        [
            [0.25, 0.25, 0.50],
            [0.20, 0.30, 0.50],
            [0.15, 0.35, 0.50],
        ],
        dtype=float,
    )

    report = build_long_probability_calibration_report(
        probabilities,
        [0, 1, 2],
        [-0.02, 0.0, 0.01],
    )

    assert report["usable_for_live_gate"] is False
    assert report["status"] == "research_only"
    assert "research-only" in report["notes"][-1]


def test_crypto_validation_returns_do_not_short_bearish_predictions() -> None:
    trainer = WalkForwardTrainer()
    sample = _TrainingSample(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        month_key=(2026, 1),
        features={},
        label=0,
        next_return=-0.08,
        symbol="BTC/USD",
    )

    crypto_returns = trainer._compute_validation_returns(
        [0],
        [0.95],
        [0],
        [sample],
        "crypto",
    )
    stock_returns = trainer._compute_validation_returns(
        [0],
        [0.95],
        [0],
        [sample],
        "stock",
    )

    assert crypto_returns == [0.0]
    assert stock_returns == [0.08]


def test_calibration_reports_baseline_and_accuracy_lift() -> None:
    probabilities = np.asarray(
        [
            [0.80, 0.10, 0.10],
            [0.20, 0.70, 0.10],
            [0.10, 0.15, 0.75],
            [0.05, 0.15, 0.80],
        ],
        dtype=float,
    )

    report = build_long_probability_calibration_report(
        probabilities,
        [0, 1, 2, 2],
        [-0.01, 0.0, 0.02, 0.03],
        minimum_high_confidence_samples=1,
    )

    assert report["baseline_class"] == 2
    assert report["baseline_class_rate"] == 0.5
    assert report["model_accuracy"] == 1.0
    assert report["accuracy_over_baseline"] == 0.5


def test_crypto_sample_weights_include_label_time_decay() -> None:
    trainer = WalkForwardTrainer()
    newest = datetime(2026, 1, 2, tzinfo=UTC)
    samples = [
        _TrainingSample(
            timestamp=newest,
            month_key=(2026, 1),
            features={},
            label=2,
            next_return=0.01,
            symbol="BTC/USD",
            label_weight=1.0,
        ),
        _TrainingSample(
            timestamp=newest,
            month_key=(2026, 1),
            features={},
            label=2,
            next_return=0.01,
            symbol="ETH/USD",
            label_weight=0.45,
        ),
        _TrainingSample(
            timestamp=newest,
            month_key=(2026, 1),
            features={},
            label=1,
            next_return=0.0,
            symbol="SOL/USD",
            label_weight=0.70,
        ),
    ]

    weights = trainer._sample_weights(
        np.asarray([sample.label for sample in samples], dtype=int),
        "crypto",
        samples,
    )

    assert weights is not None
    assert weights[0] > weights[1]
    assert weights[2] > 0.0


def test_crypto_training_skips_pre_2019_samples() -> None:
    trainer = WalkForwardTrainer()
    old_candle = Candle(
        time=datetime(2018, 12, 31, tzinfo=UTC),
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="1Day",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1_000.0,
        source="unit_test",
    )
    current_candle = Candle(
        time=datetime(2019, 1, 1, tzinfo=UTC),
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="1Day",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1_000.0,
        source="unit_test",
    )

    assert trainer._skip_training_sample(old_candle, "crypto") is True
    assert trainer._skip_training_sample(current_candle, "crypto") is False
    assert trainer._skip_training_sample(old_candle, "stock") is False
