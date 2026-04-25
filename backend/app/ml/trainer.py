"""Walk-forward LightGBM trainer for ML trading models."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
from lightgbm.basic import Booster
from numpy.typing import NDArray

from app.ml.features import (
    ALL_FEATURES,
    FeatureEngineer,
    FeatureVector,
    ResearchInputs,
    ordered_feature_row,
)
from app.models.domain import Candle

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int_]
ProgressCallback = Callable[[int, int, str], None]
ResearchLookup = Mapping[str | tuple[str, date], ResearchInputs]


@dataclass(slots=True, frozen=True)
class TrainerConfig:
    """Configuration for walk-forward model training."""

    train_months: int = 6
    test_months: int = 1
    min_confidence_threshold: float = 0.60
    lgbm_params: dict[str, object] = field(
        default_factory=lambda: {
            "objective": "multiclass",
            "num_class": 3,
            "metric": "multi_logloss",
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "feature_fraction": 0.8,
            "verbosity": -1,
        }
    )
    model_dir: str = "models"


@dataclass(slots=True, frozen=True)
class FoldResult:
    """Summary of one validation fold."""

    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    n_train_samples: int
    n_test_samples: int
    validation_accuracy: float
    validation_sharpe: float
    passed: bool
    model_path: str


@dataclass(slots=True, frozen=True)
class TrainResult:
    """Result from a walk-forward training run."""

    asset_class: str
    validation_sharpe: float
    validation_accuracy: float
    n_train_samples: int
    n_test_samples: int
    feature_importances: dict[str, float]
    model_path: str
    folds: list[FoldResult]
    fold_count: int
    best_fold_index: int


@dataclass(slots=True, frozen=True)
class _TrainingSample:
    """Internal representation of one labeled sample."""

    timestamp: datetime
    month_key: tuple[int, int]
    features: FeatureVector
    label: int
    next_return: float


class WalkForwardTrainer:
    """Train and validate LightGBM models using a sliding walk-forward window."""

    def __init__(self, config: TrainerConfig | None = None) -> None:
        self.config = config or TrainerConfig()
        self.model_dir = Path(self.config.model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    async def train(
        self,
        candles: Sequence[Candle],
        asset_class: str,
        feature_engineer: FeatureEngineer,
        research_lookup: ResearchLookup | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> TrainResult:
        """Run walk-forward validation and return the best model result."""

        samples = self._build_samples(
            candles,
            asset_class,
            feature_engineer,
            research_lookup,
        )
        if not samples:
            raise ValueError("No trainable samples were built from the provided candles")

        folds = self._build_folds(samples)
        if not folds:
            folds = [self._fallback_fold(samples)]

        fold_results: list[FoldResult] = []
        best_fold: FoldResult | None = None
        best_feature_importances: dict[str, float] | None = None

        total_folds = len(folds)
        for fold_index, fold in enumerate(folds, start=1):
            if progress_callback is not None:
                progress_callback(
                    fold_index - 1,
                    total_folds,
                    f"Training fold {fold_index}/{total_folds}",
                )

            fold_result, feature_importances = self._train_fold(asset_class, fold, fold_index)
            fold_results.append(fold_result)

            if best_fold is None or fold_result.validation_sharpe > best_fold.validation_sharpe:
                best_fold = fold_result
                best_feature_importances = feature_importances

        if progress_callback is not None:
            progress_callback(total_folds, total_folds, "Training complete")

        if best_fold is None or best_feature_importances is None:
            raise ValueError("Unable to train a valid model from the provided candles")

        return TrainResult(
            asset_class=asset_class,
            validation_sharpe=best_fold.validation_sharpe,
            validation_accuracy=best_fold.validation_accuracy,
            n_train_samples=best_fold.n_train_samples,
            n_test_samples=best_fold.n_test_samples,
            feature_importances=best_feature_importances,
            model_path=best_fold.model_path,
            folds=fold_results,
            fold_count=len(fold_results),
            best_fold_index=best_fold.fold_index,
        )

    def _build_samples(
        self,
        candles: Sequence[Candle],
        asset_class: str,
        feature_engineer: FeatureEngineer,
        research_lookup: ResearchLookup | None,
    ) -> list[_TrainingSample]:
        """Convert candles into labeled samples grouped by symbol."""

        grouped: dict[str, list[Candle]] = {}
        for candle in candles:
            if asset_class != "both" and candle.asset_class != asset_class:
                continue
            grouped.setdefault(candle.symbol, []).append(candle)

        samples: list[_TrainingSample] = []
        for symbol_candles in grouped.values():
            ordered = sorted(symbol_candles, key=lambda candle: candle.time)
            labels = self._label_candles(ordered)
            for index in range(199, len(ordered) - 1):
                research_inputs = self._research_inputs_for_sample(
                    research_lookup,
                    symbol=ordered[index].symbol,
                    sample_date=ordered[index].time.date(),
                )
                history = ordered[: index + 1]
                features = feature_engineer.build(
                    history,
                    ordered[index].asset_class,
                    research_inputs,
                )
                if features is None:
                    continue

                next_return = self._next_return(ordered[index], ordered[index + 1])
                samples.append(
                    _TrainingSample(
                        timestamp=ordered[index].time,
                        month_key=(ordered[index].time.year, ordered[index].time.month),
                        features=features,
                        label=labels[index],
                        next_return=next_return,
                    )
                )

        samples.sort(key=lambda sample: sample.timestamp)
        return samples

    def _research_inputs_for_sample(
        self,
        research_lookup: ResearchLookup | None,
        *,
        symbol: str,
        sample_date: date,
    ) -> ResearchInputs | None:
        """Return date-specific research inputs, falling back to symbol-level inputs."""

        if research_lookup is None:
            return None
        dated = research_lookup.get((symbol, sample_date))
        if dated is not None:
            return dated
        return research_lookup.get(symbol)

    def _build_folds(
        self,
        samples: Sequence[_TrainingSample],
    ) -> list[tuple[list[_TrainingSample], list[_TrainingSample]]]:
        """Create walk-forward train/test folds by calendar month."""

        months = sorted({sample.month_key for sample in samples})
        if len(months) < self.config.train_months + self.config.test_months:
            return []

        folds: list[tuple[list[_TrainingSample], list[_TrainingSample]]] = []
        step = max(1, self.config.test_months)

        for end_index in range(
            self.config.train_months,
            len(months) - self.config.test_months + 1,
            step,
        ):
            train_months = set(months[end_index - self.config.train_months : end_index])
            test_months = set(months[end_index : end_index + self.config.test_months])

            train_samples = [sample for sample in samples if sample.month_key in train_months]
            test_samples = [sample for sample in samples if sample.month_key in test_months]

            if train_samples and test_samples:
                folds.append((train_samples, test_samples))

        return folds

    def _fallback_fold(
        self,
        samples: Sequence[_TrainingSample],
    ) -> tuple[list[_TrainingSample], list[_TrainingSample]]:
        """Create a simple fallback split when there are not enough months."""

        split_index = max(1, int(len(samples) * 0.8))
        train_samples = list(samples[:split_index])
        test_samples = list(samples[split_index:])

        if not test_samples:
            test_samples = train_samples[-1:]
            train_samples = train_samples[:-1] or train_samples

        return train_samples, test_samples

    def _train_fold(
        self,
        asset_class: str,
        fold: tuple[list[_TrainingSample], list[_TrainingSample]],
        fold_index: int,
    ) -> tuple[FoldResult, dict[str, float]]:
        """Train one fold and return its validation metrics."""

        train_samples, test_samples = fold
        x_train, y_train = self._matrix(train_samples)
        x_test, y_test = self._matrix(test_samples)
        booster = self._fit_booster(x_train, y_train, x_test, y_test)

        probabilities = np.asarray(booster.predict(x_test), dtype=float)
        if probabilities.ndim == 1:
            probabilities = probabilities.reshape(1, -1)

        predictions, confidences = self._decode_predictions(probabilities)
        validation_accuracy = self._compute_accuracy(predictions, y_test.tolist())
        validation_returns = self._compute_validation_returns(
            predictions,
            confidences,
            y_test.tolist(),
            test_samples,
        )
        validation_sharpe = self._compute_sharpe(validation_returns)
        model_path = self._save_model(booster, asset_class, fold_index)
        feature_importances = self._feature_importances(booster)

        fold_result = FoldResult(
            fold_index=fold_index,
            train_start=train_samples[0].timestamp,
            train_end=train_samples[-1].timestamp,
            test_start=test_samples[0].timestamp,
            test_end=test_samples[-1].timestamp,
            n_train_samples=len(train_samples),
            n_test_samples=len(test_samples),
            validation_accuracy=validation_accuracy,
            validation_sharpe=validation_sharpe,
            passed=validation_sharpe >= 0.5,
            model_path=str(model_path),
        )

        return fold_result, feature_importances

    def _fit_booster(
        self,
        x_train: FloatArray,
        y_train: IntArray,
        x_test: FloatArray,
        y_test: IntArray,
    ) -> Booster:
        """Fit a LightGBM booster using the configured parameters."""

        params = dict(self.config.lgbm_params)
        n_estimators_value = params.pop("n_estimators", 300)
        num_boost_round = (
            int(n_estimators_value)
            if isinstance(n_estimators_value, (int, float))
            else 300
        )

        train_set = lgb.Dataset(x_train, label=y_train, feature_name=ALL_FEATURES)
        valid_set = lgb.Dataset(
            x_test,
            label=y_test,
            reference=train_set,
            feature_name=ALL_FEATURES,
        )

        callbacks: list[Callable[..., object]] = [lgb.log_evaluation(period=0)]
        if len(y_test) > 0:
            callbacks.append(lgb.early_stopping(25, verbose=False))

        return lgb.train(
            params,
            train_set,
            num_boost_round=num_boost_round,
            valid_sets=[valid_set],
            valid_names=["validation"],
            callbacks=callbacks,
        )

    def _matrix(self, samples: Sequence[_TrainingSample]) -> tuple[FloatArray, IntArray]:
        """Convert sample objects into model matrices."""

        x_values = [ordered_feature_row(sample.features) for sample in samples]
        y_values = [sample.label for sample in samples]
        x_matrix = np.asarray(x_values, dtype=float)
        y_vector = np.asarray(y_values, dtype=int)
        return x_matrix, y_vector

    def _decode_predictions(
        self,
        probabilities: FloatArray,
    ) -> tuple[list[int], list[float]]:
        """Convert class probabilities into labels with confidence thresholding."""

        labels: list[int] = []
        confidences: list[float] = []

        for row in probabilities:
            class_index = int(np.argmax(row))
            confidence = float(np.max(row))
            labels.append(1 if confidence < self.config.min_confidence_threshold else class_index)
            confidences.append(confidence)

        return labels, confidences

    def _compute_accuracy(self, predictions: Sequence[int], labels: Sequence[int]) -> float:
        """Compute classification accuracy."""

        if not labels:
            return 0.0

        correct = sum(
            int(prediction == label)
            for prediction, label in zip(predictions, labels, strict=True)
        )
        return correct / len(labels)

    def _compute_validation_returns(
        self,
        predictions: Sequence[int],
        confidences: Sequence[float],
        labels: Sequence[int],
        samples: Sequence[_TrainingSample],
    ) -> list[float]:
        """Turn predictions into per-sample strategy returns."""

        returns: list[float] = []
        for prediction, confidence, _label, sample in zip(
            predictions,
            confidences,
            labels,
            samples,
            strict=True,
        ):
            if confidence < self.config.min_confidence_threshold or prediction == 1:
                returns.append(0.0)
                continue

            direction_multiplier = -1.0 if prediction == 0 else 1.0
            returns.append(direction_multiplier * sample.next_return)

        return returns

    def _save_model(self, booster: Booster, asset_class: str, fold_index: int) -> Path:
        """Persist the trained booster to the configured model directory."""

        safe_asset_class = asset_class.replace("/", "_")
        model_path = self.model_dir / f"model_{safe_asset_class}_fold{fold_index}.lgbm"
        booster.save_model(str(model_path))
        return model_path

    def _feature_importances(self, booster: Booster) -> dict[str, float]:
        """Return normalized gain-based feature importances."""

        gains = np.asarray(booster.feature_importance(importance_type="gain"), dtype=float)
        total = float(np.sum(gains))
        if total == 0.0:
            return dict.fromkeys(ALL_FEATURES, 0.0)

        return {
            name: float(gain / total)
            for name, gain in zip(ALL_FEATURES, gains, strict=True)
        }

    def _label_candles(self, candles: Sequence[Candle]) -> list[int]:
        """Label each candle: 0=down, 1=flat, 2=up based on next-candle return."""

        labels: list[int] = []
        threshold = 0.002

        for index, candle in enumerate(candles):
            if index == len(candles) - 1:
                labels.append(1)
                continue

            next_candle = candles[index + 1]
            next_return = self._next_return(candle, next_candle)
            if next_return > threshold:
                labels.append(2)
            elif next_return < -threshold:
                labels.append(0)
            else:
                labels.append(1)

        return labels

    def _next_return(self, current: Candle, next_candle: Candle) -> float:
        """Return the next-candle percentage change."""

        if current.close == 0.0:
            return 0.0
        return (next_candle.close - current.close) / current.close

    def _compute_sharpe(self, returns: list[float]) -> float:
        """Annualised Sharpe from a list of per-trade returns."""

        if not returns:
            return 0.0

        values = np.asarray(returns, dtype=float)
        mean_return = float(np.mean(values))
        std_return = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        if std_return == 0.0:
            return 0.0

        return float(np.sqrt(252.0) * (mean_return / std_return))