"""Phase 8 Slice 20 sentiment backfill plus retrain workflow tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pytest
from fastapi import HTTPException

from app.ml import sentiment_refresh


@pytest.mark.asyncio
async def test_sentiment_refresh_forces_backfill_before_training(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refresh workflow should fetch old news and validate coverage first."""

    captured: dict[str, object] = {}

    async def _fake_backfill(
        *,
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> Mapping[str, object]:
        captured.setdefault("order", []).append("backfill")
        captured["backfill_symbols"] = symbols
        captured["backfill_start"] = start_date
        captured["backfill_end"] = end_date
        return {"status": "completed", "rows_upserted": 4}

    async def _fake_coverage(
        symbols: list[str],
        start: date,
        end: date,
        min_coverage: float,
    ) -> Mapping[str, Mapping[str, object]]:
        captured.setdefault("order", []).append("coverage")
        captured["coverage_symbols"] = symbols
        captured["coverage_start"] = start.isoformat()
        captured["coverage_end"] = end.isoformat()
        captured["min_coverage"] = min_coverage
        return {
            symbol: {
                "total_days": 3,
                "sentiment_rows": 3,
                "covered_days": 1,
                "coverage_ratio": 0.333333,
                "min_required_coverage": min_coverage,
            }
            for symbol in symbols
        }

    async def _fake_train(
        *,
        asset_class: str,
        latest_job_id: str | None,
        symbols: list[str] | None = None,
        timeframe: str = "1Day",
    ) -> tuple[Mapping[str, object], None]:
        captured.setdefault("order", []).append("train")
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
        captured.setdefault("order", []).append("predictions")
        captured["prediction_limit"] = limit
        captured["prediction_asset_class"] = asset_class
        return {
            "count": 2,
            "persisted_count": 2,
            "active_model_ids": {"crypto": "crypto-test-model"},
        }

    async def _fake_shap_summary(model_id: str) -> Mapping[str, object]:
        captured.setdefault("order", []).append("shap")
        captured["shap_model_id"] = model_id
        return {
            "model_id": model_id,
            "features": {"news_sentiment_1d": {"row_count": 2}},
            "sentiment_feature_count": 3,
        }

    monkeypatch.setattr(
        sentiment_refresh,
        "backfill_historical_crypto_sentiment",
        _fake_backfill,
    )

    response = await sentiment_refresh.run_crypto_sentiment_refresh_training(
        job_id="job-1",
        start_date="2025-01-01",
        end_date="2025-01-03",
        symbols="BTC/USD, ETH/USD, BTC/USD",
        prediction_limit=25,
        min_sentiment_coverage=0.01,
        train_model=_fake_train,
        generate_predictions=_fake_predictions,
        coverage_validator=_fake_coverage,
        shap_summary_builder=_fake_shap_summary,
    )

    assert captured["order"] == ["backfill", "coverage", "train", "predictions", "shap"]
    assert captured["backfill_symbols"] == ["BTC/USD", "ETH/USD"]
    assert captured["backfill_start"] == "2025-01-01"
    assert captured["backfill_end"] == "2025-01-03"
    assert captured["coverage_symbols"] == ["BTC/USD", "ETH/USD"]
    assert captured["min_coverage"] == 0.01
    assert captured["train_asset_class"] == "crypto"
    assert captured["prediction_asset_class"] == "crypto"
    assert captured["prediction_limit"] == 25
    assert captured["shap_model_id"] == "crypto-test-model"
    assert response["status"] == "completed"
    assert response["backfill"] == {"status": "completed", "rows_upserted": 4}
    assert response["model_id"] == "crypto-test-model"
    assert "sentiment_coverage" in response


@pytest.mark.asyncio
async def test_sentiment_refresh_blocks_training_when_coverage_is_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage validation should stop retraining when old news is too sparse."""

    captured: dict[str, object] = {"train_called": False}

    async def _fake_backfill(
        *,
        symbols: list[str],
        start_date: str,
        end_date: str,
    ) -> Mapping[str, object]:
        return {"status": "completed", "rows_upserted": 0}

    async def _fake_coverage(
        symbols: list[str],
        start: date,
        end: date,
        min_coverage: float,
    ) -> Mapping[str, Mapping[str, object]]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "insufficient_sentiment_coverage",
                "symbols": symbols,
            },
        )

    async def _fake_train(
        **_: object,
    ) -> tuple[Mapping[str, object], None]:
        captured["train_called"] = True
        return ({}, None)

    async def _fake_predictions(**_: object) -> Mapping[str, object]:
        return {}

    monkeypatch.setattr(
        sentiment_refresh,
        "backfill_historical_crypto_sentiment",
        _fake_backfill,
    )

    with pytest.raises(HTTPException) as exc_info:
        await sentiment_refresh.run_crypto_sentiment_refresh_training(
            job_id="job-1",
            start_date="2025-01-01",
            end_date="2025-01-03",
            symbols="BTC/USD",
            prediction_limit=25,
            min_sentiment_coverage=0.6,
            train_model=_fake_train,
            generate_predictions=_fake_predictions,
            coverage_validator=_fake_coverage,
        )

    assert exc_info.value.status_code == 400
    assert captured["train_called"] is False


@pytest.mark.asyncio
async def test_sentiment_refresh_rejects_invalid_date_window() -> None:
    """The operator trigger should reject inverted historical windows."""

    async def _unused_train(**_: object) -> tuple[Mapping[str, object], None]:
        return ({}, None)

    async def _unused_predictions(**_: object) -> Mapping[str, object]:
        return {}

    with pytest.raises(HTTPException) as exc_info:
        await sentiment_refresh.run_crypto_sentiment_refresh_training(
            job_id="job-1",
            start_date="2025-01-03",
            end_date="2025-01-01",
            symbols="BTC/USD",
            prediction_limit=25,
            min_sentiment_coverage=0.01,
            train_model=_unused_train,
            generate_predictions=_unused_predictions,
        )

    assert exc_info.value.status_code == 400
    assert "end_date" in str(exc_info.value.detail)
