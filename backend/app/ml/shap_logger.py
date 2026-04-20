"""SHAP explainability logging for ML trade signals."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, cast

# NEW DEP: lightgbm — reason: load persisted boosters for SHAP explainability.
import lightgbm as lgbm  # type: ignore[import-not-found]  # mypy stub unavailable in this env.

# NEW DEP: numpy — reason: matrix conversion for SHAP evaluation.
import numpy as np  # type: ignore[import-not-found]  # mypy stub unavailable in this env.

from app.ml.features import FeatureVector

# NEW DEP: shap — reason: SHAP explainability for per-trade feature attribution.
try:
    import shap  # type: ignore[import-not-found]
except ImportError:
    shap = None

class _LoggerProtocol(Protocol):
    """Minimal logging protocol used by the SHAP logger."""

    def info(self, message: str, **kwargs: object) -> None:
        ...

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:
    import logging

    _LOGGER = logging.getLogger(__name__)
    _HAS_STRUCTLOG = False

    class _FallbackLogger:
        """Fallback logger used when structlog is unavailable."""

        def info(self, message: str, **kwargs: object) -> None:
            _LOGGER.info("%s %s", message, kwargs)


def get_logger() -> _LoggerProtocol:
    """Return a structured logger or a fallback implementation."""

    if _HAS_STRUCTLOG:
        return cast(_LoggerProtocol, structlog.get_logger())
    return _FallbackLogger()


class ShapLogger:
    """Compute and log SHAP values for explainability of each trade signal."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self._booster = lgbm.Booster(model_file=model_path)
        if shap is None:
            raise RuntimeError("shap is required for ShapLogger")
        self._explainer = shap.TreeExplainer(self._booster)
        self._logger: _LoggerProtocol = get_logger()

    def log_trade_shap(
        self,
        trade_id: str,
        features: FeatureVector,
        feature_names: list[str],
    ) -> dict[str, float]:
        """Return a dict of feature_name → shap_value for the predicted class."""

        matrix = np.asarray([self._row_from_features(features, feature_names)], dtype=float)
        class_index = self._predicted_class_index(matrix)
        shap_values = self._explainer.shap_values(matrix)
        values = self._select_class_values(shap_values, class_index)
        if values is None:
            return {}
        contributions = {
            name: float(value)
            for name, value in zip(feature_names, values, strict=True)
        }
        top_features = sorted(
            contributions.items(),
            key=lambda item: abs(item[1]),
            reverse=True,
        )[:10]
        self._logger.info(
            "trade_shap",
            trade_id=trade_id,
            model_path=self.model_path,
            predicted_class=class_index,
            top_features=top_features,
        )
        return contributions

    def _row_from_features(
        self,
        features: FeatureVector,
        feature_names: Sequence[str],
    ) -> list[float]:
        """Order features according to the supplied feature name list."""

        return [float(features.get(name, 0.0)) for name in feature_names]

    def _predicted_class_index(self, matrix: np.ndarray) -> int:
        """Return the predicted class index for the provided feature row."""

        probabilities = np.asarray(self._booster.predict(matrix))
        if probabilities.ndim == 2 and probabilities.shape[0] >= 1:
            row = probabilities[0]
        elif probabilities.ndim == 1:
            row = probabilities
        else:
            return 1
        return int(np.argmax(row))

    def _select_class_values(
        self,
        shap_values: object,
        class_index: int,
    ) -> np.ndarray | None:
        """Return the SHAP vector for the predicted class."""

        if isinstance(shap_values, list):
            if class_index >= len(shap_values):
                return None
            return np.asarray(shap_values[class_index])[0]
        values = np.asarray(shap_values)
        if values.ndim == 3:
            if class_index >= values.shape[1]:
                return None
            return values[0, class_index]
        if values.ndim == 2:
            return values[0]
        return None
