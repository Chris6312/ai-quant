from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import NotRequired, TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_REGISTRY_PATH = _RUNTIME_DIR / "ml_model_registry.json"
_SUPPORTED_MODEL_SUFFIX = ".lgbm"
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_DIR = _BACKEND_DIR.parent


class FoldSummaryRecord(TypedDict):
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    validation_sharpe: float
    validation_accuracy: float
    n_train_samples: int
    n_test_samples: int
    model_path: str
    feature_names: list[str]
    feature_importances: dict[str, float]
    class_balance: dict[str, object]
    eligibility_status: str
    eligibility_reason: str


class ModelRecord(TypedDict, total=False):
    model_id: str
    asset_class: str
    status: str
    artifact_path: str
    trained_at: str
    fold_count: int
    best_fold: int
    validation_accuracy: float
    validation_sharpe: float
    train_samples: int
    test_samples: int
    feature_count: int
    confidence_threshold: float
    latest_job_id: str | None
    feature_importances: dict[str, float]
    folds: list[FoldSummaryRecord]
    selection_regime: str
    selection_policy: dict[str, object]
    class_balance: dict[str, object]
    retired_reason: NotRequired[str]
    created_at: str
    updated_at: str


def _candidate_artifact_paths(raw_path: str) -> list[Path]:
    """Return possible filesystem paths for a stored model artifact path."""

    normalized = raw_path.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        return [path]

    candidates = [
        Path.cwd() / path,
        Path.cwd() / "backend" / path,
        _BACKEND_DIR / path,
        _PROJECT_DIR / path,
        _PROJECT_DIR / "backend" / path,
    ]

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def _artifact_exists(raw_path: str) -> bool:
    """Return true when any supported candidate artifact path exists."""

    return any(candidate.exists() for candidate in _candidate_artifact_paths(raw_path))


def _is_supported_artifact_path(artifact_path: object) -> bool:
    """Return true when the registry artifact path has a supported model suffix."""

    if not isinstance(artifact_path, str) or not artifact_path:
        return False

    suffix = Path(artifact_path.replace("\\", "/")).suffix.lower()
    return suffix == _SUPPORTED_MODEL_SUFFIX


def _is_registerable_model_record(model: ModelRecord) -> bool:
    """Return true for records that may be written into the registry."""

    return _is_supported_artifact_path(model.get("artifact_path"))


def _is_visible_model_record(model: ModelRecord) -> bool:
    """Return false for placeholder or missing active artifacts that must not surface."""

    artifact_path = model.get("artifact_path")
    if not _is_supported_artifact_path(artifact_path):
        return False

    if model.get("status") == "active" and isinstance(artifact_path, str):
        return _artifact_exists(artifact_path)

    return True


def _parse_feature_names(line: str) -> list[str]:
    prefix = "feature_names="
    if not line.startswith(prefix):
        return []
    return [name for name in line.removeprefix(prefix).split(" ") if name]


def _parse_int_values(line: str, prefix: str) -> list[int]:
    if not line.startswith(prefix):
        return []

    values: list[int] = []
    for raw_value in line.removeprefix(prefix).split(" "):
        if not raw_value:
            continue
        try:
            values.append(int(raw_value))
        except ValueError:
            continue
    return values


def _parse_float_values(line: str, prefix: str) -> list[float]:
    if not line.startswith(prefix):
        return []

    values: list[float] = []
    for raw_value in line.removeprefix(prefix).split(" "):
        if not raw_value:
            continue
        try:
            values.append(float(raw_value))
        except ValueError:
            continue
    return values


def _load_feature_importances_from_artifact_text(
    text: str,
    expected_feature_names: list[str] | None = None,
) -> dict[str, float]:
    """Parse normalized gain-based feature importances from a LightGBM text model."""

    feature_names: list[str] = []
    gains_by_index: dict[int, float] = {}
    pending_split_features: list[int] = []

    for line in text.splitlines():
        if line.startswith("feature_names="):
            feature_names = _parse_feature_names(line)
            continue

        if line.startswith("split_feature="):
            pending_split_features = _parse_int_values(line, "split_feature=")
            continue

        if line.startswith("split_gain="):
            split_gains = _parse_float_values(line, "split_gain=")
            for feature_index, gain in zip(
                pending_split_features,
                split_gains,
                strict=False,
            ):
                gains_by_index[feature_index] = gains_by_index.get(feature_index, 0.0) + gain
            pending_split_features = []

    if not feature_names and expected_feature_names:
        feature_names = expected_feature_names

    if not feature_names:
        return {}

    total_gain = sum(gains_by_index.values())
    if total_gain <= 0.0:
        return dict.fromkeys(feature_names, 0.0)

    importances: dict[str, float] = {}
    for index, name in enumerate(feature_names):
        gain = gains_by_index.get(index, 0.0)
        importances[name] = float(gain / total_gain)

    return importances


def load_feature_importances_from_artifact_path(
    raw_path: str,
    expected_feature_names: list[str] | None = None,
) -> dict[str, float]:
    """Load normalized gain-based feature importances from a model artifact."""

    if not _is_supported_artifact_path(raw_path):
        return {}

    for candidate in _candidate_artifact_paths(raw_path):
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue

        importances = _load_feature_importances_from_artifact_text(
            text,
            expected_feature_names,
        )
        if importances:
            return importances

    return {}


def _fold_with_loaded_importances(fold: FoldSummaryRecord) -> FoldSummaryRecord:
    existing_importances = fold.get("feature_importances", {})
    if existing_importances:
        return fold

    model_path = fold.get("model_path", "")
    if not model_path:
        return fold

    loaded_importances = load_feature_importances_from_artifact_path(model_path)
    if not loaded_importances:
        return fold

    return {
        **fold,
        "feature_importances": loaded_importances,
    }


def _model_with_loaded_importances(model: ModelRecord) -> ModelRecord:
    enriched_model: ModelRecord = {**model}

    artifact_path = enriched_model.get("artifact_path", "")
    existing_importances = enriched_model.get("feature_importances", {})
    if isinstance(artifact_path, str) and not existing_importances:
        loaded_importances = load_feature_importances_from_artifact_path(artifact_path)
        if loaded_importances:
            enriched_model["feature_importances"] = loaded_importances
            enriched_model["feature_count"] = len(loaded_importances)

    folds = enriched_model.get("folds", [])
    if folds:
        enriched_model["folds"] = [
            _fold_with_loaded_importances(fold)
            for fold in folds
        ]

    return enriched_model


def _load_registry_unlocked() -> list[ModelRecord]:
    if not _REGISTRY_PATH.exists():
        return []
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    models = cast(list[ModelRecord], data)
    visible_models = [model for model in models if _is_visible_model_record(model)]
    return [_model_with_loaded_importances(model) for model in visible_models]


def _save_registry_unlocked(models: list[ModelRecord]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(models, indent=2), encoding="utf-8")


def register_model(model: ModelRecord) -> ModelRecord:
    now = datetime.now(UTC).isoformat()
    record: ModelRecord = {
        **model,
        "created_at": model.get("created_at", now),
        "updated_at": now,
    }
    if not _is_registerable_model_record(record):
        artifact_path = record.get("artifact_path")
        raise ValueError(f"Refusing to register invalid model artifact: {artifact_path}")

    record = _model_with_loaded_importances(record)

    with _LOCK:
        models = _load_registry_unlocked()
        for existing in models:
            if (
                existing.get("asset_class") == record.get("asset_class")
                and existing.get("status") == "active"
            ):
                existing["status"] = "retired"
                existing["updated_at"] = now
        models.insert(0, record)
        _save_registry_unlocked(models)
    return record


def list_models(asset_class: str | None = None) -> list[ModelRecord]:
    with _LOCK:
        models = _load_registry_unlocked()
    if asset_class is None:
        return models
    return [model for model in models if model.get("asset_class") == asset_class]


def get_model(model_id: str) -> ModelRecord | None:
    with _LOCK:
        models = _load_registry_unlocked()
    return next((model for model in models if model.get("model_id") == model_id), None)


def get_active_model(asset_class: str) -> ModelRecord | None:
    with _LOCK:
        models = _load_registry_unlocked()
    return next(
        (
            model
            for model in models
            if model.get("asset_class") == asset_class and model.get("status") == "active"
        ),
        None,
    )


def retire_active_models(asset_class: str, reason: str) -> list[ModelRecord]:
    """Mark all active models for an asset class as retired."""

    now = datetime.now(UTC).isoformat()
    retired: list[ModelRecord] = []

    with _LOCK:
        models = _load_registry_unlocked()
        for model in models:
            if (
                model.get("asset_class") == asset_class
                and model.get("status") == "active"
            ):
                model["status"] = "retired"
                model["retired_reason"] = reason
                model["updated_at"] = now
                retired.append(model)
        _save_registry_unlocked(models)

    return retired