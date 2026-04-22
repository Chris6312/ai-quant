"""LightGBM model prediction helpers."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgbm
import numpy as np
from numpy.typing import NDArray

from app.ml.features import FeatureVector, ordered_feature_row

FloatArray = NDArray[np.float64]


@dataclass(slots=True, frozen=True)
class PredictionResult:
    """Prediction output for one candle window."""

    direction: str
    confidence: float
    class_probs: tuple[float, float, float]


class ModelPredictor:
    """Load a trained LightGBM model and produce per-candle confidence scores."""

    def __init__(self, model_path: str, min_confidence: float = 0.60) -> None:
        self.model_path = model_path
        self.min_confidence = min_confidence
        self._booster = lgbm.Booster(model_file=model_path)

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
        )

    def _vectorize(self, features: FeatureVector) -> list[float]:
        """Convert a feature dictionary into an ordered numeric row."""

        return ordered_feature_row(features)

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

    def _direction_for_class(self, class_index: int) -> str:
        """Map class index to trading direction."""

        if class_index == 0:
            return "short"
        if class_index == 1:
            return "flat"
        return "long"