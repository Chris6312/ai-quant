"""Phase 8 Slice 20 sentiment backfill plus retrain workflow tests."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import HTTPException

from app.api.routers import ml as ml_router


@pytest.mark.asyncio
async def test_sentiment_refresh_triggers_backfill_train_predictions_and_shap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator trigger should fetch old news before retraining and SHAP review."""

    captured: dict[str, object] = {}

    async def _fake_backfill(
        *,
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> Mapping[str, object]:
        captured["backfill_symbols"] = symbols
        captured["backfill_start"] = start_date
        captured["backfill_end"] = end_date
        return {"status": "completed", "rows_upserted": 4}

    async def _fake_train(
        *,
        asset_class: str,
        latest_job_id: str | None,
        symbols: list[str] | None = None,
        timeframe: str = "1Day",
    ) -> tuple[Mapping[str, object], None]:
        captured["train_asset_class"] = asset_class
        captured["train_job_id"] = latest_job_id
        captured["train_symbols"] = symbols
        captured["train_timeframe"] = timeframe
        return (
            {
                "model_id": "crypto-test-model",
                "asset_class": "crypto",
                "status": "active",
                "artifact_path": "models/crypto_test.txt",
                "best_fold": 1,
                "fold_count": 2,
                "validation_accuracy": 0.61,
                "validation_sharpe": 1.23,
                "train_samples": 100,
                "test_samples": 20,
                "feature_count": 25,
            },
            None,
        )

    async def _fake_predictions(
        *,
        limit: int = 200,
        asset_class: str | None = None,
    ) -> Mapping[str, object]:
        captured["prediction_limit"] = limit
        captured["prediction_asset_class"] = asset_class
        return {
            "count": 2,
            "persisted_count": 2,
            "active_model_ids": {"crypto": "crypto-test-model"},
        }

    async def _fake_shap_summary(model_id: str) -> Mapping[str, object]:
        captured["shap_model_id"] = model_id
        return {
            "model_id": model_id,
            "features": {"news_sentiment_1d": {"row_count": 2}},
            "sentiment_feature_count": 3,
        }

    monkeypatch.setattr(ml_router, "_ensure_no_running_job", lambda: None)
    monkeypatch.setattr(ml_router, "_new_job", lambda _name, _symbols: {"job_id": "job-1"})
    monkeypatch.setattr(ml_router, "backfill_historical_crypto_sentiment", _fake_backfill)
    monkeypatch.setattr(ml_router, "_run_registered_training_job", _fake_train)
    monkeypatch.setattr(ml_router, "generate_prediction_snapshot", _fake_predictions)
    monkeypatch.setattr(ml_router, "_build_sentiment_shap_summary", _fake_shap_summary)

    response = await ml_router.train_crypto_after_sentiment_backfill(
        start_date="2025-01-01",
        end_date="2025-01-03",
        symbols="BTC/USD, ETH/USD, BTC/USD",
        prediction_limit=25,
        skip_backfill=False,
    )

    assert captured["backfill_symbols"] == ["BTC/USD", "ETH/USD"]
    assert captured["backfill_start"] == "2025-01-01"
    assert captured["backfill_end"] == "2025-01-03"
    assert captured["train_asset_class"] == "crypto"
    assert captured["prediction_asset_class"] == "crypto"
    assert captured["prediction_limit"] == 25
    assert captured["shap_model_id"] == "crypto-test-model"
    assert response["status"] == "completed"
    assert response["backfill"] == {"status": "completed", "rows_upserted": 4}
    assert response["model_id"] == "crypto-test-model"


@pytest.mark.asyncio
async def test_sentiment_refresh_rejects_invalid_date_window() -> None:
    """The operator trigger should reject inverted historical windows."""

    with pytest.raises(HTTPException) as exc_info:
        await ml_router.train_crypto_after_sentiment_backfill(
            start_date="2025-01-03",
            end_date="2025-01-01",
        )

    assert exc_info.value.status_code == 400
    assert "end_date" in str(exc_info.value.detail)
