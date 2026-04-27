"""LightGBM model prediction helpers."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgbm
import numpy as np
from numpy.typing import NDArray

from app.ml.features import FeatureVector

FloatArray = NDArray[np.float64]


@dataclass(slots=True, frozen=True)
class PredictionResult:
    """Prediction output for one candle window."""

    direction: str
    confidence: float
    class_probs: tuple[float, float, float]
    class_index: int


class ModelPredictor:
    """Load a trained LightGBM model and produce per-candle confidence scores."""

    def __init__(self, model_path: str, min_confidence: float = 0.60) -> None:
        self.model_path = model_path
        self.min_confidence = min_confidence
        self._booster = lgbm.Booster(model_file=model_path)
        self._feature_names = list(self._booster.feature_name())

    def predict(self, features: FeatureVector) -> PredictionResult | None:
        """Return a prediction or None when confidence is below threshold."""

        row = np.asarray([self._vectorize(features)], dtype=float)
        probabilities = np.asarray(self._booster.predict(row), dtype=float)
        class_probs = self._extract_class_probs(probabilities)
        if class_probs is None:
            return None

        confidence = max(class_probs)
        if confidence < self.min_confidence:
            return None

        class_index = int(np.argmax(class_probs))
        direction = self._direction_for_class(class_index)
        return PredictionResult(
            direction=direction,
            confidence=confidence,
            class_probs=class_probs,
            class_index=class_index,
        )

    def explain(
        self,
        features: FeatureVector,
        *,
        class_index: int,
    ) -> dict[str, float]:
        """Return LightGBM contribution values for the predicted class."""

        row = np.asarray([self._vectorize(features)], dtype=float)
        raw_contribs = np.asarray(self._booster.predict(row, pred_contrib=True), dtype=float)
        contribs = self._extract_class_contributions(raw_contribs, class_index)
        if contribs is None:
            return {}
        return {
            feature_name: float(contrib)
            for feature_name, contrib in zip(self._feature_names, contribs, strict=True)
        }

    def _vectorize(self, features: FeatureVector) -> list[float]:
        """Convert a feature dictionary into an ordered numeric row."""

        return [float(features.get(name, 0.0)) for name in self._feature_names]

    def _extract_class_probs(
        self,
        probabilities: FloatArray,
    ) -> tuple[float, float, float] | None:
        """Normalize LightGBM output into a 3-class probability tuple."""

        if probabilities.ndim == 2 and probabilities.shape[0] >= 1:
            row = probabilities[0]
        elif probabilities.ndim == 1:
            row = probabilities
        else:
            return None

        if row.shape[0] != 3:
            return None

        return (float(row[0]), float(row[1]), float(row[2]))

    def _extract_class_contributions(
        self,
        contributions: FloatArray,
        class_index: int,
    ) -> FloatArray | None:
        """Normalize LightGBM contribution output into one feature vector."""

        feature_count_with_bias = len(self._feature_names) + 1
        if contributions.ndim == 3 and contributions.shape[0] >= 1:
            if class_index >= contributions.shape[1]:
                return None
            class_contributions = np.asarray(
                contributions[0, class_index, :-1],
                dtype=np.float64,
            )
            return class_contributions

        if contributions.ndim != 2 or contributions.shape[0] < 1:
            return None

        row = contributions[0]
        if row.shape[0] == feature_count_with_bias:
            direct_contributions = np.asarray(row[:-1], dtype=np.float64)
            return direct_contributions

        expected_multiclass_width = 3 * feature_count_with_bias
        if row.shape[0] == expected_multiclass_width:
            start = class_index * feature_count_with_bias
            end = start + len(self._feature_names)
            multiclass_contributions = np.asarray(row[start:end], dtype=np.float64)
            return multiclass_contributions

        return None

    def _direction_for_class(self, class_index: int) -> str:
        """Map class index to trading direction."""

        if class_index == 0:
            return "short"
        if class_index == 1:
            return "flat"
        return "long"
