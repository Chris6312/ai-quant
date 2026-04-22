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
from app.ml.trainer import FoldResult, TrainerConfig, TrainResult
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

    async def _fake_load(asset_class: str) -> list[Candle]:
        assert asset_class == "crypto"
        return candles

    monkeypatch.setattr(ml_router, "_load_training_candles", _fake_load)
    monkeypatch.setattr(ml_router, "WalkForwardTrainer", _FakeTrainer)

    job = ml_router._new_job("crypto_train", ["BTC/USD"])
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