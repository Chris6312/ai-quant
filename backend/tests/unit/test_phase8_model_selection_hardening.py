"""Phase 8 model selection hardening tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.ml.trainer import FoldResult, TrainerConfig, WalkForwardTrainer
from app.models.domain import Candle


def _fold(
    *,
    index: int,
    test_end: datetime,
    sharpe: float,
    accuracy: float,
    samples: int,
    model_path: Path,
) -> FoldResult:
    model_path.write_text("fake model", encoding="utf-8")
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
        accuracy=0.296,
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
