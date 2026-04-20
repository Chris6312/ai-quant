"""Feature-importance drift monitoring for ML model versions."""

from __future__ import annotations

from dataclasses import dataclass

from app.ml.features import RESEARCH_FEATURES

try:
    import structlog  # type: ignore[import-not-found]  # optional dependency in some environments.

    _LOGGER = structlog.get_logger(__name__)

    def _log_warning(event: str, **context: object) -> None:
        _LOGGER.warning(event, **context)
except ImportError:
    import logging

    _LOGGER = logging.getLogger(__name__)

    def _log_warning(event: str, **context: object) -> None:
        _LOGGER.warning("%s %s", event, context)


_TOP_FEATURE_COUNT: int = 10


@dataclass(slots=True, frozen=True)
class DriftReport:
    """Summary of feature-importance drift between model versions."""

    asset_class: str
    previous_top_features: list[str]
    current_top_features: list[str]
    importance_delta: dict[str, float]
    drift_detected: bool
    drift_threshold: float


class DriftMonitor:
    """Compare feature importance between consecutive model versions."""

    def __init__(self, drift_threshold: float = 0.20) -> None:
        self.drift_threshold = drift_threshold

    def check(
        self,
        previous: dict[str, float],
        current: dict[str, float],
        asset_class: str,
    ) -> DriftReport:
        """Return a drift report for the supplied model importances."""

        importance_delta = self._importance_delta(previous, current)
        drift_detected = False
        for feature in RESEARCH_FEATURES:
            delta = importance_delta.get(feature, 0.0)
            if delta < -self.drift_threshold:
                drift_detected = True
                _log_warning(
                    "research_feature_importance_drift",
                    asset_class=asset_class,
                    feature=feature,
                    previous=previous.get(feature, 0.0),
                    current=current.get(feature, 0.0),
                    delta=delta,
                    threshold=self.drift_threshold,
                )
        return DriftReport(
            asset_class=asset_class,
            previous_top_features=self._top_features(previous),
            current_top_features=self._top_features(current),
            importance_delta=importance_delta,
            drift_detected=drift_detected,
            drift_threshold=self.drift_threshold,
        )

    def _importance_delta(
        self,
        previous: dict[str, float],
        current: dict[str, float],
    ) -> dict[str, float]:
        """Compute current-minus-previous importance deltas for all features."""

        return {
            feature: current.get(feature, 0.0) - previous.get(feature, 0.0)
            for feature in sorted(set(previous) | set(current))
        }

    def _top_features(self, importances: dict[str, float]) -> list[str]:
        """Return the top features ranked by importance."""

        ordered = sorted(importances.items(), key=lambda item: item[1], reverse=True)
        return [feature for feature, _ in ordered[:_TOP_FEATURE_COUNT]]
