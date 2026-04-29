"""Probability calibration diagnostics for ML validation folds."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

import numpy as np
from numpy.typing import NDArray

from app.ml.labels import PROFIT_TARGET_LABEL

FloatArray = NDArray[np.float64]


class CalibrationBucket(TypedDict):
    """One probability bucket from validation/test fold scoring."""

    label: str
    lower: float
    upper: float
    count: int
    predicted_probability_mean: float
    actual_win_rate: float
    false_positive_rate: float
    expected_value_proxy: float


class CalibrationReport(TypedDict):
    """Validation/test-only probability calibration summary."""

    status: str
    usable_for_live_gate: bool
    dead_zone_lower: float
    dead_zone_upper: float
    sample_count: int
    bucket_count: int
    high_confidence_count: int
    high_confidence_win_rate: float
    dead_zone_count: int
    dead_zone_win_rate: float
    separation: float
    false_positive_rate: float
    expected_value_proxy: float
    baseline_class: int
    baseline_class_rate: float
    model_accuracy: float
    accuracy_over_baseline: float
    buckets: list[CalibrationBucket]
    notes: list[str]


_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0.00-0.40", 0.0, 0.40),
    ("0.40-0.50", 0.40, 0.50),
    ("0.50-0.60", 0.50, 0.60),
    ("0.60-0.70", 0.60, 0.70),
    ("0.70+", 0.70, 1.01),
)


def build_long_probability_calibration_report(
    probabilities: FloatArray,
    labels: Sequence[int],
    returns: Sequence[float],
    *,
    dead_zone_lower: float = 0.40,
    dead_zone_upper: float = 0.60,
    minimum_high_confidence_samples: int = 30,
    minimum_separation: float = 0.05,
) -> CalibrationReport:
    """Compare predicted long probability with actual long-label success rate.

    The report is built only from the validation/test fold. It treats class 2 as
    the long profit-target class, so weak probabilities remain a dead-zone
    diagnostic instead of a live ALLOW signal.
    """

    long_probabilities = _long_probabilities(probabilities)
    normalized_labels = [int(label) for label in labels]
    normalized_returns = [float(value) for value in returns]
    sample_count = min(
        len(long_probabilities),
        len(normalized_labels),
        len(normalized_returns),
    )
    if sample_count == 0:
        return _empty_report(dead_zone_lower, dead_zone_upper)

    long_probabilities = long_probabilities[:sample_count]
    normalized_labels = normalized_labels[:sample_count]
    normalized_returns = normalized_returns[:sample_count]

    buckets = [
        _build_bucket(
            label=bucket_label,
            lower=lower,
            upper=upper,
            probabilities=long_probabilities,
            labels=normalized_labels,
            returns=normalized_returns,
        )
        for bucket_label, lower, upper in _BUCKETS
    ]
    high_indexes = [
        index
        for index, probability in enumerate(long_probabilities)
        if probability >= dead_zone_upper
    ]
    dead_zone_indexes = [
        index
        for index, probability in enumerate(long_probabilities)
        if dead_zone_lower <= probability < dead_zone_upper
    ]
    low_indexes = [
        index
        for index, probability in enumerate(long_probabilities)
        if probability < dead_zone_lower
    ]

    high_win_rate = _win_rate(high_indexes, normalized_labels)
    dead_zone_win_rate = _win_rate(dead_zone_indexes, normalized_labels)
    low_win_rate = _win_rate(low_indexes, normalized_labels)
    comparison_win_rate = dead_zone_win_rate if dead_zone_indexes else low_win_rate
    separation = high_win_rate - comparison_win_rate if high_indexes else 0.0
    false_positive_rate = _false_positive_rate(high_indexes, normalized_labels)
    expected_value_proxy = _average_return(high_indexes, normalized_returns)
    baseline_class, baseline_class_rate = _majority_class_rate(normalized_labels)
    model_accuracy = _model_accuracy(long_probabilities, probabilities, normalized_labels)
    accuracy_over_baseline = model_accuracy - baseline_class_rate

    notes: list[str] = [
        "Calibration uses validation/test fold rows only.",
        "Class 2 is treated as long profit-target success.",
        "Probabilities inside 0.40-0.60 stay in the dead zone and cannot create ALLOW.",
    ]
    usable = (
        len(high_indexes) >= minimum_high_confidence_samples
        and separation >= minimum_separation
        and high_win_rate > dead_zone_win_rate
    )
    if not usable:
        notes.append("Model remains research-only until probability separation improves.")

    return {
        "status": "calibrated" if usable else "research_only",
        "usable_for_live_gate": usable,
        "dead_zone_lower": dead_zone_lower,
        "dead_zone_upper": dead_zone_upper,
        "sample_count": sample_count,
        "bucket_count": len(buckets),
        "high_confidence_count": len(high_indexes),
        "high_confidence_win_rate": high_win_rate,
        "dead_zone_count": len(dead_zone_indexes),
        "dead_zone_win_rate": dead_zone_win_rate,
        "separation": separation,
        "false_positive_rate": false_positive_rate,
        "expected_value_proxy": expected_value_proxy,
        "baseline_class": baseline_class,
        "baseline_class_rate": baseline_class_rate,
        "model_accuracy": model_accuracy,
        "accuracy_over_baseline": accuracy_over_baseline,
        "buckets": buckets,
        "notes": notes,
    }


def _long_probabilities(probabilities: FloatArray) -> list[float]:
    matrix = np.asarray(probabilities, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.shape[1] <= PROFIT_TARGET_LABEL:
        return [0.0 for _row in matrix]
    return [float(row[PROFIT_TARGET_LABEL]) for row in matrix]


def _build_bucket(
    *,
    label: str,
    lower: float,
    upper: float,
    probabilities: Sequence[float],
    labels: Sequence[int],
    returns: Sequence[float],
) -> CalibrationBucket:
    indexes = [
        index
        for index, probability in enumerate(probabilities)
        if lower <= probability < upper
    ]
    return {
        "label": label,
        "lower": lower,
        "upper": upper,
        "count": len(indexes),
        "predicted_probability_mean": _average(indexes, probabilities),
        "actual_win_rate": _win_rate(indexes, labels),
        "false_positive_rate": _false_positive_rate(indexes, labels),
        "expected_value_proxy": _average_return(indexes, returns),
    }


def _empty_report(dead_zone_lower: float, dead_zone_upper: float) -> CalibrationReport:
    return {
        "status": "research_only",
        "usable_for_live_gate": False,
        "dead_zone_lower": dead_zone_lower,
        "dead_zone_upper": dead_zone_upper,
        "sample_count": 0,
        "bucket_count": 0,
        "high_confidence_count": 0,
        "high_confidence_win_rate": 0.0,
        "dead_zone_count": 0,
        "dead_zone_win_rate": 0.0,
        "separation": 0.0,
        "false_positive_rate": 0.0,
        "expected_value_proxy": 0.0,
        "baseline_class": 1,
        "baseline_class_rate": 0.0,
        "model_accuracy": 0.0,
        "accuracy_over_baseline": 0.0,
        "buckets": [],
        "notes": ["No validation/test rows were available for calibration."],
    }


def _average(indexes: Sequence[int], values: Sequence[float]) -> float:
    if not indexes:
        return 0.0
    return sum(values[index] for index in indexes) / len(indexes)


def _average_return(indexes: Sequence[int], returns: Sequence[float]) -> float:
    return _average(indexes, returns)


def _win_rate(indexes: Sequence[int], labels: Sequence[int]) -> float:
    if not indexes:
        return 0.0
    wins = sum(1 for index in indexes if labels[index] == PROFIT_TARGET_LABEL)
    return wins / len(indexes)


def _false_positive_rate(indexes: Sequence[int], labels: Sequence[int]) -> float:
    if not indexes:
        return 0.0
    false_positives = sum(1 for index in indexes if labels[index] != PROFIT_TARGET_LABEL)
    return false_positives / len(indexes)


def _majority_class_rate(labels: Sequence[int]) -> tuple[int, float]:
    if not labels:
        return 1, 0.0
    counts = {0: 0, 1: 0, 2: 0}
    for label in labels:
        counts[int(label)] = counts.get(int(label), 0) + 1
    majority_class, count = max(counts.items(), key=lambda item: (item[1], -item[0]))
    return majority_class, count / len(labels)


def _model_accuracy(
    long_probabilities: Sequence[float],
    probabilities: FloatArray,
    labels: Sequence[int],
) -> float:
    if not labels:
        return 0.0
    matrix = np.asarray(probabilities, dtype=float)[: len(labels)]
    if matrix.ndim == 1 or matrix.shape[1] <= PROFIT_TARGET_LABEL:
        predicted = [PROFIT_TARGET_LABEL if value >= 0.5 else 1 for value in long_probabilities]
    else:
        predicted = [int(np.argmax(row)) for row in matrix]
    hits = sum(
        1
        for expected, actual in zip(labels, predicted, strict=True)
        if expected == actual
    )
    return hits / len(labels)
