"""Phase 8 model selection hardening tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from app.ml.trainer import (
    FoldResult,
    NoEligibleProductionFoldError,
    TrainerConfig,
    WalkForwardTrainer,
)
from app.models.domain import Candle


def _fold(
    *,
    index: int,
    test_end: datetime,
    sharpe: float,
    accuracy: float,
    samples: int,
    model_path: Path,
    class_counts: dict[int, int] | None = None,
) -> FoldResult:
    model_path.write_text("fake model", encoding="utf-8")
    counts = class_counts or {0: 120, 1: 180, 2: 120}
    majority_class = max(counts, key=lambda label: counts[label])
    baseline_accuracy = counts[majority_class] / sum(counts.values())
    return FoldResult(
        fold_index=index,
        train_start=test_end - timedelta(days=180),
        train_end=test_end - timedelta(days=31),
        test_start=test_end - timedelta(days=30),
        test_end=test_end,
        n_train_samples=2_700,
        n_test_samples=samples,
        validation_accuracy=accuracy,
        validation_sharpe=sharpe,
        passed=sharpe >= 0.5,
        model_path=str(model_path),
        class_counts=counts,
        majority_class=majority_class,
        majority_class_baseline_accuracy=baseline_accuracy,
        baseline_margin=accuracy - baseline_accuracy,
    )


def _stable_crypto_candles() -> list[Candle]:
    start = datetime(2025, 10, 1, tzinfo=UTC)
    candles: list[Candle] = []
    price = 100.0
    for index in range(130):
        price += 0.2
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol="BTC/USD",
                asset_class="crypto",
                timeframe="1Day",
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=10_000.0,
                source="test",
            )
        )
    return candles


def _volatile_crypto_candles() -> list[Candle]:
    start = datetime(2025, 10, 1, tzinfo=UTC)
    candles: list[Candle] = []
    price = 120.0
    for index in range(130):
        if index >= 105:
            price *= 0.985
        else:
            price += 0.1
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol="BTC/USD",
                asset_class="crypto",
                timeframe="1Day",
                open=price,
                high=price * 1.04,
                low=price * 0.96,
                close=price,
                volume=10_000.0,
                source="test",
            )
        )
    return candles


def test_crypto_selector_promotes_recent_eligible_fold_over_ancient_high_sharpe(
    tmp_path: Path,
) -> None:
    """Old high-Sharpe folds should be research-only for production crypto models."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    ancient = _fold(
        index=6,
        test_end=datetime(2015, 3, 31, tzinfo=UTC),
        sharpe=4.48,
        accuracy=0.90,
        samples=500,
        model_path=tmp_path / "model_crypto_fold6.lgbm",
    )
    recent = _fold(
        index=138,
        test_end=datetime(2026, 3, 31, tzinfo=UTC),
        sharpe=1.79,
        accuracy=0.56,
        samples=465,
        model_path=tmp_path / "model_crypto_fold138.lgbm",
    )
    low_accuracy = _fold(
        index=139,
        test_end=datetime(2026, 4, 24, tzinfo=UTC),
        sharpe=2.63,
        accuracy=0.175,
        samples=360,
        model_path=tmp_path / "model_crypto_fold139.lgbm",
    )

    selection = trainer._select_production_fold(
        asset_class="crypto",
        candles=_stable_crypto_candles(),
        folds=[ancient, recent, low_accuracy],
    )

    assert selection.best_fold.fold_index == 138
    by_index = {fold.fold_index: fold for fold in selection.folds}
    assert by_index[6].eligibility_status == "research_only"
    assert by_index[6].eligibility_reason == "too_old_for_current_regime"
    assert by_index[139].eligibility_status == "research_only"
    assert by_index[139].eligibility_reason == "accuracy_below_threshold"
    assert by_index[138].eligibility_status == "active"


def test_crypto_regime_uses_shorter_window_when_very_volatile(tmp_path: Path) -> None:
    """Very volatile crypto conditions should reduce fold eligibility to 180 days."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    regime = trainer._detect_crypto_regime(_volatile_crypto_candles())

    assert regime.regime == "very_volatile"
    assert regime.max_fold_age_days == 180
    assert regime.reasons


def test_crypto_selector_rejects_fold_below_majority_class_baseline(
    tmp_path: Path,
) -> None:
    """Crypto production folds must beat the naive majority-class baseline."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    baseline_failure = _fold(
        index=140,
        test_end=datetime(2026, 4, 24, tzinfo=UTC),
        sharpe=2.1,
        accuracy=0.50,
        samples=465,
        model_path=tmp_path / "model_crypto_fold140.lgbm",
        class_counts={0: 50, 1: 260, 2: 155},
    )

    status, reason = trainer._crypto_fold_eligibility(
        baseline_failure,
        min_test_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )

    assert status == "research_only"
    assert reason == "accuracy_not_above_majority_baseline"


def test_crypto_selector_rejects_fold_without_baseline_buffer(
    tmp_path: Path,
) -> None:
    """Crypto folds need enough accuracy margin above the naive baseline."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    thin_margin = _fold(
        index=141,
        test_end=datetime(2026, 4, 24, tzinfo=UTC),
        sharpe=2.1,
        accuracy=0.58,
        samples=465,
        model_path=tmp_path / "model_crypto_fold141.lgbm",
        class_counts={0: 50, 1: 260, 2: 155},
    )

    status, reason = trainer._crypto_fold_eligibility(
        thin_margin,
        min_test_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )

    assert status == "research_only"
    assert reason == "accuracy_margin_below_baseline_buffer"


def test_crypto_training_uses_balanced_sample_weights(tmp_path: Path) -> None:
    """Crypto training should not let the majority class dominate unchecked."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    labels = [0, 1, 1, 1, 2]
    weights = trainer._sample_weights(
        np.asarray(labels, dtype=int),
        "crypto",
    )

    assert weights is not None
    assert weights[0] > weights[1]
    assert weights[4] > weights[1]
    assert trainer._sample_weights(
        np.asarray(labels, dtype=int),
        "stock",
    ) is None



def test_crypto_selector_raises_structured_no_eligible_error(
    tmp_path: Path,
) -> None:
    """No eligible crypto fold should be a structured outcome, not an opaque crash."""

    trainer = WalkForwardTrainer(TrainerConfig(model_dir=str(tmp_path)))
    low_accuracy = _fold(
        index=139,
        test_end=datetime(2026, 4, 24, tzinfo=UTC),
        sharpe=2.64,
        accuracy=0.175,
        samples=465,
        model_path=tmp_path / "model_crypto_fold139.lgbm",
    )

    try:
        trainer._select_production_fold(
            asset_class="crypto",
            candles=_stable_crypto_candles(),
            folds=[low_accuracy],
        )
    except NoEligibleProductionFoldError as exc:
        assert str(exc) == (
            "No production-eligible recent crypto fold passed model selection policy"
        )
        assert exc.regime in {"normal", "normal_stable", "very_volatile"}
        assert exc.policy["min_validation_accuracy"] == 0.35
        assert len(exc.folds) == 1
        assert exc.folds[0].eligibility_status == "research_only"
        assert exc.folds[0].eligibility_reason == "accuracy_below_threshold"
    else:
        raise AssertionError("Expected NoEligibleProductionFoldError")
