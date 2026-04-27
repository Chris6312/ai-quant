"""Phase 6 ML training orchestration tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routers import ml as ml_router
from app.main import app
from app.ml import job_store, model_registry
from app.ml.features import FeatureEngineer
from app.ml.trainer import (
    FoldResult,
    NoEligibleProductionFoldError,
    TrainerConfig,
    TrainResult,
)
from app.models.domain import Candle


class _FakeTrainer:
    def __init__(self, config: TrainerConfig) -> None:
        self.config = config

    async def train(
        self,
        candles: list[Candle],
        asset_class: str,
        feature_engineer: FeatureEngineer,
        research_lookup: Mapping[str, object] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> TrainResult:
        del candles
        del feature_engineer
        del research_lookup

        if progress_callback is not None:
            progress_callback(1, 2, "Training fold 1/2")
            progress_callback(2, 2, "Training fold 2/2")

        model_dir = Path(self.config.model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)

        fold1_path = model_dir / f"model_{asset_class}_fold1.lgbm"
        fold2_path = model_dir / f"model_{asset_class}_fold2.lgbm"
        fold1_path.write_text("fake model 1", encoding="utf-8")
        fold2_path.write_text("fake model 2", encoding="utf-8")

        return TrainResult(
            asset_class=asset_class,
            validation_sharpe=1.24,
            validation_accuracy=0.68,
            n_train_samples=180,
            n_test_samples=40,
            feature_importances={
                "rsi_14": 0.31,
                "returns_5": 0.27,
                "macd_hist": 0.21,
            },
            model_path=str(fold2_path),
            folds=[
                FoldResult(
                    fold_index=1,
                    train_start=datetime(2025, 1, 1, tzinfo=UTC),
                    train_end=datetime(2025, 6, 30, tzinfo=UTC),
                    test_start=datetime(2025, 7, 1, tzinfo=UTC),
                    test_end=datetime(2025, 7, 31, tzinfo=UTC),
                    n_train_samples=180,
                    n_test_samples=40,
                    validation_accuracy=0.66,
                    validation_sharpe=0.91,
                    passed=True,
                    model_path=str(fold1_path),
                ),
                FoldResult(
                    fold_index=2,
                    train_start=datetime(2025, 2, 1, tzinfo=UTC),
                    train_end=datetime(2025, 7, 31, tzinfo=UTC),
                    test_start=datetime(2025, 8, 1, tzinfo=UTC),
                    test_end=datetime(2025, 8, 31, tzinfo=UTC),
                    n_train_samples=180,
                    n_test_samples=40,
                    validation_accuracy=0.68,
                    validation_sharpe=1.24,
                    passed=True,
                    model_path=str(fold2_path),
                ),
            ],
            fold_count=2,
            best_fold_index=2,
        )


@pytest.mark.asyncio
async def test_run_training_job_registers_active_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed training run should finish the job and write a registry record."""

    runtime_dir = tmp_path / ".runtime"
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_dir / "ml_jobs.json")
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )

    candles = [
        Candle(
            time=datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
            symbol="BTC/USD",
            asset_class="crypto",
            timeframe="1Day",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10_000.0,
            source="crypto_csv_training",
        )
        for index in range(260)
    ]

    async def _fake_train_crypto_model_from_db(
        session: object,
        *,
        symbols: list[str] | None = None,
    ) -> tuple[TrainResult, object]:
        del session
        assert symbols is None
        result = await _FakeTrainer(TrainerConfig()).train(
            candles,
            "crypto",
            FeatureEngineer(),
        )
        return result, object()

    monkeypatch.setattr(
        ml_router,
        "train_crypto_model_from_db_impl",
        _fake_train_crypto_model_from_db,
    )

    job = ml_router._new_job("crypto_train", [ml_router.ALL_CRYPTO_TRAINING_SYMBOL])
    await ml_router._run_training_job(str(job["job_id"]), "crypto")

    stored_job = job_store.get_job(str(job["job_id"]))
    assert stored_job is not None
    assert stored_job["status"] == "done"
    assert stored_job["result"] is not None
    assert stored_job["result"]["best_fold"] == 2

    models = model_registry.list_models("crypto")
    assert len(models) == 1
    assert models[0]["status"] == "active"
    assert models[0]["best_fold"] == 2
    assert len(models[0]["folds"]) == 2



@pytest.mark.asyncio
async def test_train_crypto_endpoint_uses_all_crypto_metadata_and_no_symbol_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crypto training should advertise ALL_CRYPTO and pass no symbol filter downstream."""

    runtime_dir = tmp_path / ".runtime"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "model_crypto_fold2.lgbm").write_text("fake model", encoding="utf-8")
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_dir / "ml_jobs.json")
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(model_registry, "_BACKEND_DIR", tmp_path)
    monkeypatch.setattr(model_registry, "_PROJECT_DIR", tmp_path)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )
    monkeypatch.setattr(ml_router, "load_jobs", lambda: job_store.list_jobs())

    captured_symbols: list[str] | None | object = object()

    async def _fake_train_crypto_model_from_db(
        session: object,
        *,
        symbols: list[str] | None = None,
    ) -> tuple[TrainResult, object]:
        nonlocal captured_symbols
        del session
        captured_symbols = symbols
        return (
            TrainResult(
                asset_class="crypto",
                validation_sharpe=1.24,
                validation_accuracy=0.68,
                n_train_samples=180,
                n_test_samples=40,
                feature_importances={"returns_5": 0.27},
                model_path="models/model_crypto_fold2.lgbm",
                folds=[],
                fold_count=2,
                best_fold_index=2,
            ),
            object(),
        )

    class _FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object,
        ) -> None:
            del exc_type, exc, tb
            return None

    monkeypatch.setattr(ml_router, "get_settings", lambda: object())
    monkeypatch.setattr(ml_router, "build_engine", lambda settings: object())
    monkeypatch.setattr(ml_router, "build_session_factory", lambda engine: lambda: _FakeSession())
    monkeypatch.setattr(
        ml_router,
        "train_crypto_model_from_db_impl",
        _fake_train_crypto_model_from_db,
    )

    client = TestClient(app)
    response = client.post("/ml/train/crypto")

    assert response.status_code == 200
    assert captured_symbols is None
    jobs = job_store.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["symbols"] == [ml_router.ALL_CRYPTO_TRAINING_SYMBOL]


@pytest.mark.asyncio
async def test_train_crypto_endpoint_returns_no_model_selected_when_guardrails_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Training guardrail rejection should be a 200 outcome, not a 500 error."""

    runtime_dir = tmp_path / ".runtime"
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_dir / "ml_jobs.json")
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )
    monkeypatch.setattr(ml_router, "load_jobs", lambda: job_store.list_jobs())

    fold = FoldResult(
        fold_index=139,
        train_start=datetime(2025, 9, 30, tzinfo=UTC),
        train_end=datetime(2026, 3, 30, tzinfo=UTC),
        test_start=datetime(2026, 4, 1, tzinfo=UTC),
        test_end=datetime(2026, 4, 23, tzinfo=UTC),
        n_train_samples=2_700,
        n_test_samples=465,
        validation_accuracy=0.175,
        validation_sharpe=2.64,
        passed=False,
        model_path="models/model_crypto_fold139.lgbm",
        eligibility_status="research_only",
        eligibility_reason="accuracy_below_threshold",
    )

    async def _fake_train_crypto_result() -> TrainResult:
        raise NoEligibleProductionFoldError(
            "No production-eligible recent crypto fold passed model selection policy",
            folds=[fold],
            regime="normal",
            policy={"min_validation_accuracy": 0.35},
        )

    monkeypatch.setattr(ml_router, "_train_crypto_result", _fake_train_crypto_result)

    client = TestClient(app)
    response = client.post("/ml/train/crypto")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_model_selected"
    assert payload["outcome"] == "no_model_selected"
    assert payload["fold_count"] == 1
    assert payload["folds"][0]["eligibility_reason"] == "accuracy_below_threshold"

    jobs = job_store.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "done"
    assert jobs[0]["result"] is not None
    assert jobs[0]["result"]["outcome"] == "no_model_selected"

def test_train_endpoint_blocks_when_job_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting training should fail fast when another ML job is already running."""

    monkeypatch.setattr(
        ml_router,
        "load_jobs",
        lambda: [
            {
                "job_id": "running-job",
                "type": "stock_backfill",
                "asset_class": "stock",
                "symbols": ["AAPL"],
                "status": "running",
                "started_at": "2026-04-21T12:00:00+00:00",
                "finished_at": None,
                "total_symbols": 1,
                "done_symbols": 0,
                "current_symbol": "AAPL",
                "total_batches": 1,
                "done_batches": 0,
                "rows_fetched": 0,
                "current_timeframe": "1Day",
                "status_message": "busy",
                "progress_pct": 10,
                "error": None,
                "result": None,
            }
        ],
    )

    client = TestClient(app)
    response = client.post("/ml/train/crypto")

    assert response.status_code == 409
    assert response.json()["detail"] == "another ML job is already running"

def test_get_model_importances_endpoint_returns_sorted_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Feature importance endpoint should expose sorted live weights for the UI."""

    runtime_dir = tmp_path / ".runtime"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "model_crypto_fold2.lgbm").write_text("fake model", encoding="utf-8")
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(model_registry, "_BACKEND_DIR", tmp_path)
    monkeypatch.setattr(model_registry, "_PROJECT_DIR", tmp_path)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )

    model_registry.register_model(
        {
            "model_id": "crypto-model-1",
            "asset_class": "crypto",
            "status": "active",
            "artifact_path": "models/model_crypto_fold2.lgbm",
            "trained_at": "2026-04-22T10:00:00+00:00",
            "fold_count": 2,
            "best_fold": 2,
            "validation_accuracy": 0.68,
            "validation_sharpe": 1.24,
            "train_samples": 180,
            "test_samples": 40,
            "feature_count": 3,
            "confidence_threshold": 0.6,
            "latest_job_id": "job-1",
            "feature_importances": {
                "macd_hist": 0.21,
                "rsi_14": 0.31,
                "returns_5": 0.27,
            },
            "folds": [],
            "created_at": "2026-04-22T10:00:00+00:00",
        }
    )

    client = TestClient(app)
    response = client.get("/ml/models/crypto-model-1/importances")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_id"] == "crypto-model-1"
    assert payload["feature_count"] == 3
    assert [row["feature"] for row in payload["importances"]] == [
        "rsi_14",
        "returns_5",
        "macd_hist",
    ]



def test_model_registry_rejects_and_filters_stock_txt_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder stock .txt artifacts should never register or surface as active models."""

    runtime_dir = tmp_path / ".runtime"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "model_crypto_fold2.lgbm").write_text("fake model", encoding="utf-8")
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(model_registry, "_BACKEND_DIR", tmp_path)
    monkeypatch.setattr(model_registry, "_PROJECT_DIR", tmp_path)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )

    with pytest.raises(ValueError, match="invalid model artifact"):
        model_registry.register_model(
            {
                "model_id": "stock-placeholder",
                "asset_class": "stock",
                "status": "active",
                "artifact_path": "models/stock_fold_0.txt",
                "trained_at": "2026-04-25T10:00:00+00:00",
                "fold_count": 0,
                "best_fold": 0,
                "validation_accuracy": 0.72,
                "validation_sharpe": 1.5,
                "train_samples": 200,
                "test_samples": 40,
                "feature_count": 1,
                "confidence_threshold": 0.6,
                "latest_job_id": "job-1",
                "feature_importances": {"news_sentiment_7d": 4.0},
                "folds": [],
                "created_at": "2026-04-25T10:00:00+00:00",
            }
        )

    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "ml_model_registry.json").write_text(
        """[
          {
            "model_id": "stock-placeholder",
            "asset_class": "stock",
            "status": "active",
            "artifact_path": "models/stock_fold_0.txt"
          },
          {
            "model_id": "crypto-real",
            "asset_class": "crypto",
            "status": "active",
            "artifact_path": "models/model_crypto_fold2.lgbm"
          }
        ]""",
        encoding="utf-8",
    )

    assert model_registry.list_models("stock") == []
    assert model_registry.get_active_model("stock") is None
    assert model_registry.get_active_model("crypto") is not None


def test_model_registry_ignores_active_models_with_missing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active records should not surface when their .lgbm artifact is missing."""

    runtime_dir = tmp_path / ".runtime"
    monkeypatch.setattr(model_registry, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(model_registry, "_BACKEND_DIR", tmp_path)
    monkeypatch.setattr(model_registry, "_PROJECT_DIR", tmp_path)
    monkeypatch.setattr(
        model_registry,
        "_REGISTRY_PATH",
        runtime_dir / "ml_model_registry.json",
    )

    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "ml_model_registry.json").write_text(
        """[
          {
            "model_id": "crypto-missing",
            "asset_class": "crypto",
            "status": "active",
            "artifact_path": "models/model_crypto_missing.lgbm"
          },
          {
            "model_id": "stock-missing",
            "asset_class": "stock",
            "status": "active",
            "artifact_path": "models/model_stock_missing.lgbm"
          }
        ]""",
        encoding="utf-8",
    )

    assert model_registry.list_models() == []
    assert model_registry.get_active_model("crypto") is None
    assert model_registry.get_active_model("stock") is None


def test_feature_parity_endpoint_reports_valid_contract() -> None:
    """Parity endpoint should confirm asset-specific contracts are valid."""

    client = TestClient(app)
    response = client.get("/ml/features/parity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["parity_ok"] is True
    assert payload["same_feature_order"] is False
    assert payload["stock_contract_valid"] is True
    assert payload["crypto_contract_valid"] is True
    assert payload["feature_count"] > 0
