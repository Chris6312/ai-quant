"""Phase 8 tests for persisted ML prediction API reads."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import HTTPException

from app.api.routers import ml as ml_router


@pytest.mark.asyncio
async def test_get_predictions_reads_persisted_snapshot_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /ml/predictions must read persisted rows and never rebuild predictions."""

    captured: dict[str, object] = {}

    async def _fake_read_persisted_prediction_snapshot(
        *,
        limit: int,
        asset_class: str | None,
    ) -> Mapping[str, object]:
        captured["limit"] = limit
        captured["asset_class"] = asset_class
        return {
            "predictions": [],
            "count": 0,
            "active_model_ids": {"crypto": None, "stock": None},
            "freshness_by_asset": {
                "crypto": {
                    "latest_candle_time": None,
                    "lag_days": None,
                    "is_stale": True,
                    "status": "no_data",
                }
            },
            "generated_at": "2026-04-24T20:20:00+00:00",
            "source": "persisted",
        }

    async def _fail_if_generation_runs(
        *,
        limit: int = 200,
        asset_class: str | None = None,
    ) -> Mapping[str, object]:
        del limit, asset_class
        raise AssertionError("GET /ml/predictions must not generate predictions")

    monkeypatch.setattr(
        ml_router,
        "_read_persisted_prediction_snapshot",
        _fake_read_persisted_prediction_snapshot,
    )
    monkeypatch.setattr(
        ml_router,
        "generate_prediction_snapshot",
        _fail_if_generation_runs,
    )

    response = await ml_router.get_predictions(limit=15, asset_class="crypto")

    assert captured == {"limit": 15, "asset_class": "crypto"}
    assert response["source"] == "persisted"
    assert response["predictions"] == []


@pytest.mark.asyncio
async def test_get_predictions_rejects_invalid_asset_class_before_db_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid asset classes should fail before any persisted-read work starts."""

    async def _fail_if_read_runs(
        *,
        limit: int,
        asset_class: str | None,
    ) -> Mapping[str, object]:
        del limit, asset_class
        raise AssertionError("Invalid asset class should not reach the DB read path")

    monkeypatch.setattr(
        ml_router,
        "_read_persisted_prediction_snapshot",
        _fail_if_read_runs,
    )

    with pytest.raises(HTTPException) as exc_info:
        await ml_router.get_predictions(limit=15, asset_class="forex")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "asset_class must be crypto or stock"


@pytest.mark.asyncio
async def test_run_predictions_is_the_only_generation_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /ml/predictions/run should remain the explicit generation path."""

    captured: dict[str, object] = {}

    async def _fake_generate_prediction_snapshot(
        *,
        limit: int = 200,
        asset_class: str | None = None,
    ) -> Mapping[str, object]:
        captured["limit"] = limit
        captured["asset_class"] = asset_class
        return {
            "predictions": [],
            "count": 0,
            "persisted_count": 0,
            "source": "generated",
        }

    monkeypatch.setattr(
        ml_router,
        "generate_prediction_snapshot",
        _fake_generate_prediction_snapshot,
    )

    response = await ml_router.run_predictions(limit=25, asset_class="crypto")

    assert captured == {"limit": 25, "asset_class": "crypto"}
    assert response["source"] == "generated"
