"""Walk-forward LightGBM trainer for ML trading models."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import lightgbm as lgb
import numpy as np
from lightgbm.basic import Booster, LightGBMError
from numpy.typing import NDArray

from app.ml.features import (
    FeatureEngineer,
    FeatureVector,
    ResearchInputs,
    feature_names_for_asset_class,
    ordered_feature_row,
)
from app.models.domain import Candle

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int_]
ProgressCallback = Callable[[int, int, str], None]
ResearchLookup = Mapping[str | tuple[str, date], ResearchInputs]

def _model_path_candidates(model_path: str) -> list[Path]:
    """Return possible filesystem paths for a persisted fold model artifact."""

    raw_path = Path(model_path)
    if raw_path.is_absolute():
        return [raw_path]

    backend_dir = Path(__file__).resolve().parents[2]
    project_dir = backend_dir.parent
    return [
        raw_path,
        backend_dir / raw_path,
        project_dir / raw_path,
    ]


def load_feature_importances_from_model_path(
    model_path: str,
    feature_names: list[str],
) -> dict[str, float]:
    """Best-effort feature importance loader for legacy model records."""

    for candidate in _model_path_candidates(model_path):
        try:
            booster = lgb.Booster(model_file=str(candidate))
            model_feature_names = booster.feature_name()
            names = model_feature_names if model_feature_names else feature_names
            return _normalized_gain_importances(booster, names)
        except (LightGBMError, FileNotFoundError, ValueError):
            continue

    return {}


def _normalized_gain_importances(
    booster: Booster,
    feature_names: Sequence[str],
) -> dict[str, float]:
    """Return normalized gain-based feature importances for a fitted booster."""

    gains = np.asarray(booster.feature_importance(importance_type="gain"), dtype=float)
    names = list(feature_names)
    if len(names) != len(gains):
        names = [f"feature_{index}" for index in range(len(gains))]

    total = float(np.sum(gains))
    if total == 0.0:
        return dict.fromkeys(names, 0.0)

    return {
        name: float(gain / total)
        for name, gain in zip(names, gains, strict=True)
    }


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
    crypto_normal_max_age_days: int = 365
    crypto_volatile_max_age_days: int = 180
    crypto_min_validation_sharpe: float = 0.0
    crypto_min_validation_accuracy: float = 0.35
    crypto_min_baseline_margin: float = 0.03
    stock_label_threshold: float = 0.002
    crypto_label_threshold: float = 0.0075
    crypto_min_test_samples: int = 300
    crypto_volatility_ratio_threshold: float = 1.35
    crypto_max_drawdown_threshold: float = -0.20
    crypto_atr_percentile_threshold: float = 0.80


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
    class_counts: dict[int, int] = field(default_factory=dict)
    majority_class: int = 1
    majority_class_baseline_accuracy: float = 0.0
    baseline_margin: float = 0.0
    feature_names: list[str] = field(default_factory=list)
    feature_importances: dict[str, float] = field(default_factory=dict)
    eligibility_status: str = "research_only"
    eligibility_reason: str = "not_evaluated"


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
    selection_regime: str = "not_evaluated"
    selection_policy: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class _TrainingSample:
    """Internal representation of one labeled sample."""

    timestamp: datetime
    month_key: tuple[int, int]
    features: FeatureVector
    label: int
    next_return: float
    symbol: str


@dataclass(slots=True, frozen=True)
class CryptoRegimeSnapshot:
    """Current crypto regime inputs used to choose production fold age."""

    regime: str
    max_fold_age_days: int
    btc_realized_vol_30d: float
    btc_realized_vol_90d: float
    btc_volatility_ratio: float
    btc_max_drawdown_30d: float
    average_atr_pct_14: float
    atr_percentile_rank: float
    reasons: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class FoldSelectionResult:
    """Result of applying production fold eligibility rules."""

    best_fold: FoldResult
    folds: list[FoldResult]
    regime: str
    policy: dict[str, object]


class NoEligibleProductionFoldError(ValueError):
    """Raised when training completes but no fold is safe for production."""

    def __init__(
        self,
        message: str,
        *,
        folds: Sequence[FoldResult],
        regime: str,
        policy: Mapping[str, object],
    ) -> None:
        super().__init__(message)
        self.folds = list(folds)
        self.regime = regime
        self.policy = dict(policy)


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
        feature_importances_by_fold: dict[int, dict[str, float]] = {}

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
            feature_importances_by_fold[fold_result.fold_index] = feature_importances

        if progress_callback is not None:
            progress_callback(total_folds, total_folds, "Training complete")

        selection = self._select_production_fold(
            asset_class=asset_class,
            candles=candles,
            folds=fold_results,
        )
        fold_results = selection.folds
        best_fold = selection.best_fold
        best_feature_importances = feature_importances_by_fold.get(best_fold.fold_index)

        if best_feature_importances is None:
            raise ValueError("Unable to train a valid model from the selected fold")

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
            selection_regime=selection.regime,
            selection_policy=selection.policy,
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
            labels = self._label_candles(ordered, ordered[0].asset_class)
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
                        symbol=ordered[index].symbol,
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

        candidate: ResearchInputs | None = None
        closest_date: date | None = None

        for key, value in research_lookup.items():
            if not isinstance(key, tuple):
                continue

            key_symbol, key_date = key
            if key_symbol == symbol and key_date <= sample_date and (
                closest_date is None or key_date > closest_date
            ):
                closest_date = key_date
                candidate = value

        if candidate is not None:
            return candidate

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
        feature_names = feature_names_for_asset_class(asset_class)
        x_train, y_train = self._matrix(train_samples, asset_class)
        x_test, y_test = self._matrix(test_samples, asset_class)
        booster = self._fit_booster(
            x_train,
            y_train,
            x_test,
            y_test,
            feature_names,
            asset_class,
        )

        probabilities = np.asarray(booster.predict(x_test), dtype=float)
        if probabilities.ndim == 1:
            probabilities = probabilities.reshape(1, -1)

        predictions, confidences = self._decode_predictions(probabilities)
        validation_accuracy = self._compute_accuracy(predictions, y_test.tolist())
        class_counts = self._class_counts(y_test.tolist())
        majority_class, baseline_accuracy = self._majority_class_baseline(
            y_test.tolist()
        )
        baseline_margin = validation_accuracy - baseline_accuracy
        validation_returns = self._compute_validation_returns(
            predictions,
            confidences,
            y_test.tolist(),
            test_samples,
        )
        validation_sharpe = self._compute_sharpe(validation_returns)
        model_path = self._save_model(booster, asset_class, fold_index)
        persisted_feature_names = booster.feature_name() or feature_names
        feature_importances = self._feature_importances(
            booster,
            persisted_feature_names,
        )

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
            class_counts=class_counts,
            majority_class=majority_class,
            majority_class_baseline_accuracy=baseline_accuracy,
            baseline_margin=baseline_margin,
            feature_names=list(persisted_feature_names),
            feature_importances=feature_importances,
        )

        return fold_result, feature_importances

    def _select_production_fold(
        self,
        *,
        asset_class: str,
        candles: Sequence[Candle],
        folds: Sequence[FoldResult],
    ) -> FoldSelectionResult:
        """Select the active production fold after applying age and quality gates."""

        if not folds:
            raise ValueError("Unable to train a valid model from the provided candles")

        if asset_class != "crypto":
            best = max(folds, key=lambda fold: fold.validation_sharpe)
            stock_labeled = [
                replace(
                    fold,
                    eligibility_status=(
                        "active" if fold.fold_index == best.fold_index else "eligible"
                    ),
                    eligibility_reason="stock_selection_highest_sharpe",
                )
                for fold in folds
            ]
            active = next(
                fold for fold in stock_labeled if fold.fold_index == best.fold_index
            )
            return FoldSelectionResult(
                best_fold=active,
                folds=stock_labeled,
                regime="not_applicable",
                policy={"selector": "highest_validation_sharpe"},
            )

        regime = self._detect_crypto_regime(candles)
        reference_date = datetime.now(UTC).date()
        min_test_end = reference_date - timedelta(days=regime.max_fold_age_days)
        eligible: list[FoldResult] = []
        labeled: list[FoldResult] = []

        for fold in folds:
            status, reason = self._crypto_fold_eligibility(
                fold,
                min_test_end=min_test_end,
            )
            updated = replace(fold, eligibility_status=status, eligibility_reason=reason)
            labeled.append(updated)
            if status == "eligible":
                eligible.append(updated)

        policy: dict[str, object] = {
            "selector": "highest_recent_eligible_validation_sharpe",
            "regime": regime.regime,
            "max_fold_age_days": regime.max_fold_age_days,
            "min_test_end": min_test_end.isoformat(),
            "min_validation_sharpe": self.config.crypto_min_validation_sharpe,
            "min_validation_accuracy": self.config.crypto_min_validation_accuracy,
            "min_baseline_margin": self.config.crypto_min_baseline_margin,
            "min_test_samples": self.config.crypto_min_test_samples,
            "btc_realized_vol_30d": regime.btc_realized_vol_30d,
            "btc_realized_vol_90d": regime.btc_realized_vol_90d,
            "btc_volatility_ratio": regime.btc_volatility_ratio,
            "btc_max_drawdown_30d": regime.btc_max_drawdown_30d,
            "average_atr_pct_14": regime.average_atr_pct_14,
            "atr_percentile_rank": regime.atr_percentile_rank,
            "regime_reasons": list(regime.reasons),
        }

        if not eligible:
            raise NoEligibleProductionFoldError(
                "No production-eligible recent crypto fold passed model selection policy",
                folds=labeled,
                regime=regime.regime,
                policy=policy,
            )

        best = max(eligible, key=lambda fold: fold.validation_sharpe)
        labeled = [
            replace(
                fold,
                eligibility_status="active",
                eligibility_reason="selected_highest_recent_sharpe",
            )
            if fold.fold_index == best.fold_index
            else fold
            for fold in labeled
        ]
        active = next(fold for fold in labeled if fold.fold_index == best.fold_index)
        return FoldSelectionResult(
            best_fold=active,
            folds=labeled,
            regime=regime.regime,
            policy=policy,
        )

    def _crypto_fold_eligibility(
        self,
        fold: FoldResult,
        *,
        min_test_end: date,
    ) -> tuple[str, str]:
        """Return production eligibility label and reason for one crypto fold."""

        if fold.test_end.date() < min_test_end:
            return "research_only", "too_old_for_current_regime"
        if fold.validation_sharpe <= self.config.crypto_min_validation_sharpe:
            return "research_only", "sharpe_not_positive"
        if fold.validation_accuracy < self.config.crypto_min_validation_accuracy:
            return "research_only", "accuracy_below_threshold"
        if fold.validation_accuracy <= fold.majority_class_baseline_accuracy:
            return "research_only", "accuracy_not_above_majority_baseline"
        if fold.baseline_margin < self.config.crypto_min_baseline_margin:
            return "research_only", "accuracy_margin_below_baseline_buffer"
        if fold.n_test_samples < self.config.crypto_min_test_samples:
            return "research_only", "insufficient_test_samples"
        if not Path(fold.model_path).exists():
            return "research_only", "missing_artifact"
        return "eligible", "passes_production_policy"

    def _detect_crypto_regime(self, candles: Sequence[Candle]) -> CryptoRegimeSnapshot:
        """Detect whether current crypto conditions require a shorter fold age window."""

        crypto_candles = [candle for candle in candles if candle.asset_class == "crypto"]
        btc_candles = sorted(
            (
                candle
                for candle in crypto_candles
                if candle.symbol.upper() in {"BTC/USD", "BTCUSD", "XBT/USD", "XBTUSD"}
            ),
            key=lambda candle: candle.time,
        )
        btc_closes = [candle.close for candle in btc_candles if candle.close > 0]
        btc_returns = self._daily_returns(btc_closes)
        btc_vol_30d = self._realized_volatility(btc_returns[-30:])
        btc_vol_90d = self._realized_volatility(btc_returns[-90:])
        btc_ratio = btc_vol_30d / btc_vol_90d if btc_vol_90d > 0 else 0.0
        btc_drawdown = self._max_drawdown(btc_closes[-30:])
        atr_values = self._atr_pct_values(crypto_candles)
        recent_atr = self._recent_average(atr_values, 30)
        atr_percentile = self._percentile_rank(atr_values, recent_atr)

        reasons: list[str] = []
        if btc_ratio > self.config.crypto_volatility_ratio_threshold:
            reasons.append("btc_30d_vol_gt_90d_vol_threshold")
        if btc_drawdown <= self.config.crypto_max_drawdown_threshold:
            reasons.append("btc_30d_drawdown_below_threshold")
        if atr_percentile >= self.config.crypto_atr_percentile_threshold:
            reasons.append("average_atr_pct_above_percentile_threshold")

        very_volatile = len(reasons) > 0
        return CryptoRegimeSnapshot(
            regime="very_volatile" if very_volatile else "normal_stable",
            max_fold_age_days=(
                self.config.crypto_volatile_max_age_days
                if very_volatile
                else self.config.crypto_normal_max_age_days
            ),
            btc_realized_vol_30d=btc_vol_30d,
            btc_realized_vol_90d=btc_vol_90d,
            btc_volatility_ratio=btc_ratio,
            btc_max_drawdown_30d=btc_drawdown,
            average_atr_pct_14=recent_atr,
            atr_percentile_rank=atr_percentile,
            reasons=tuple(reasons),
        )

    def _daily_returns(self, closes: Sequence[float]) -> list[float]:
        """Return close-to-close percentage returns."""

        returns: list[float] = []
        for previous, current in pairwise(closes):
            if previous <= 0:
                continue
            returns.append((current - previous) / previous)
        return returns

    def _realized_volatility(self, returns: Sequence[float]) -> float:
        """Return daily realized volatility for the supplied return window."""

        if len(returns) < 2:
            return 0.0
        return float(np.std(np.asarray(returns, dtype=float), ddof=1))

    def _max_drawdown(self, closes: Sequence[float]) -> float:
        """Return the most negative drawdown in a close-price window."""

        if not closes:
            return 0.0
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak <= 0:
                continue
            drawdown = (close - peak) / peak
            max_drawdown = min(max_drawdown, drawdown)
        return max_drawdown

    def _atr_pct_values(self, candles: Sequence[Candle]) -> list[float]:
        """Compute simple ATR percent values by symbol for regime detection."""

        grouped: dict[str, list[Candle]] = {}
        for candle in candles:
            if candle.asset_class != "crypto":
                continue
            grouped.setdefault(candle.symbol, []).append(candle)

        atr_values: list[float] = []
        for rows in grouped.values():
            ordered = sorted(rows, key=lambda candle: candle.time)
            true_ranges: list[float] = []
            previous_close: float | None = None
            for candle in ordered:
                high_low = candle.high - candle.low
                if previous_close is None:
                    true_range = high_low
                else:
                    true_range = max(
                        high_low,
                        abs(candle.high - previous_close),
                        abs(candle.low - previous_close),
                    )
                true_ranges.append(true_range)
                if len(true_ranges) >= 14 and candle.close > 0:
                    atr = float(np.mean(np.asarray(true_ranges[-14:], dtype=float)))
                    atr_values.append(atr / candle.close)
                previous_close = candle.close
        return atr_values

    def _recent_average(self, values: Sequence[float], window: int) -> float:
        """Return average of the most recent values."""

        if not values:
            return 0.0
        recent = values[-window:]
        return float(np.mean(np.asarray(recent, dtype=float)))

    def _percentile_rank(self, values: Sequence[float], target: float) -> float:
        """Return the percentile rank of target within values as 0.0-1.0."""

        if not values:
            return 0.0
        count = sum(1 for value in values if value <= target)
        return count / len(values)

    def _fit_booster(
        self,
        x_train: FloatArray,
        y_train: IntArray,
        x_test: FloatArray,
        y_test: IntArray,
        feature_names: list[str],
        asset_class: str,
    ) -> Booster:
        """Fit a LightGBM booster using the configured parameters."""

        params = dict(self.config.lgbm_params)
        n_estimators_value = params.pop("n_estimators", 300)
        num_boost_round = (
            int(n_estimators_value)
            if isinstance(n_estimators_value, (int, float))
            else 300
        )

        sample_weights = self._sample_weights(y_train, asset_class)
        train_set = lgb.Dataset(
            x_train,
            label=y_train,
            weight=sample_weights,
            feature_name=feature_names,
        )
        valid_set = lgb.Dataset(
            x_test,
            label=y_test,
            reference=train_set,
            feature_name=feature_names,
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

    def _sample_weights(
        self,
        labels: IntArray,
        asset_class: str,
    ) -> FloatArray | None:
        """Return balanced sample weights for crypto multiclass training."""

        if asset_class.lower().strip() != "crypto" or len(labels) == 0:
            return None

        counts = self._class_counts(labels.tolist())
        class_count = 3
        sample_count = len(labels)
        weights_by_class: dict[int, float] = {}
        for label in range(class_count):
            count = counts.get(label, 0)
            if count <= 0:
                weights_by_class[label] = 0.0
            else:
                weights_by_class[label] = sample_count / (class_count * count)

        return np.asarray(
            [weights_by_class[int(label)] for label in labels],
            dtype=float,
        )

    def _class_counts(self, labels: Sequence[int]) -> dict[int, int]:
        """Return counts for each multiclass label."""

        counts = {0: 0, 1: 0, 2: 0}
        for label in labels:
            counts[int(label)] = counts.get(int(label), 0) + 1
        return counts

    def _majority_class_baseline(self, labels: Sequence[int]) -> tuple[int, float]:
        """Return naive majority-class label and accuracy baseline."""

        if not labels:
            return 1, 0.0

        counts = self._class_counts(labels)
        majority_class, majority_count = max(
            counts.items(),
            key=lambda item: (item[1], -item[0]),
        )
        return majority_class, majority_count / len(labels)

    def _matrix(
        self,
        samples: Sequence[_TrainingSample],
        asset_class: str,
    ) -> tuple[FloatArray, IntArray]:
        """Convert sample objects into model matrices."""

        x_values = [ordered_feature_row(sample.features, asset_class) for sample in samples]
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

    def _feature_importances(
        self,
        booster: Booster,
        feature_names: list[str],
    ) -> dict[str, float]:
        """Return normalized gain-based feature importances."""

        return _normalized_gain_importances(booster, feature_names)

    def _label_candles(self, candles: Sequence[Candle], asset_class: str) -> list[int]:
        """Label each candle: 0=down, 1=flat, 2=up based on next-candle return."""

        labels: list[int] = []
        threshold = self._label_threshold(asset_class)

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

    def _label_threshold(self, asset_class: str) -> float:
        """Return the class boundary threshold for the requested asset class."""

        if asset_class.lower().strip() == "crypto":
            return self.config.crypto_label_threshold
        return self.config.stock_label_threshold

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
