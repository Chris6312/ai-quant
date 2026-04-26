from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

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


def _load_registry_unlocked() -> list[ModelRecord]:
    if not _REGISTRY_PATH.exists():
        return []
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    models = cast(list[ModelRecord], data)
    return [model for model in models if _is_visible_model_record(model)]


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
