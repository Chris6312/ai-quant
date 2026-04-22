from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_REGISTRY_PATH = _RUNTIME_DIR / "ml_model_registry.json"


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
    created_at: str
    updated_at: str


def _load_registry_unlocked() -> list[ModelRecord]:
    if not _REGISTRY_PATH.exists():
        return []
    data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return cast(list[ModelRecord], data)



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
