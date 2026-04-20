# backend/tests/unit/test_phase3_ml_persistence.py
"""Phase 3 ML persistence tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routers import ml as ml_router
from app.main import app
from app.ml import job_store


def test_job_store_persists_and_sorts_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ML job ledger should persist to disk and sort newest first."""

    runtime_dir = tmp_path / ".runtime"
    runtime_file = runtime_dir / "ml_jobs.json"
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_file)

    first = job_store.create_job(
        {
            "job_id": "older-job",
            "type": "backfill_stocks",
            "asset_class": "stock",
            "symbols": ["AAPL"],
            "status": "running",
            "started_at": datetime(2026, 4, 20, 12, 0, tzinfo=UTC).isoformat(),
            "finished_at": None,
            "total_symbols": 1,
            "done_symbols": 0,
            "current_symbol": None,
            "total_batches": 1,
            "done_batches": 0,
            "rows_fetched": 0,
            "current_timeframe": None,
            "status_message": "Queued",
            "progress_pct": 0,
            "error": None,
            "result": None,
        }
    )
    newer = job_store.create_job(
        {
            "job_id": "newer-job",
            "type": "backfill_crypto",
            "asset_class": "crypto",
            "symbols": ["BTCUSD"],
            "status": "running",
            "started_at": datetime(2026, 4, 20, 12, 30, tzinfo=UTC).isoformat(),
            "finished_at": None,
            "total_symbols": 1,
            "done_symbols": 0,
            "current_symbol": None,
            "total_batches": 1,
            "done_batches": 0,
            "rows_fetched": 0,
            "current_timeframe": None,
            "status_message": "Queued",
            "progress_pct": 0,
            "error": None,
            "result": None,
        }
    )

    assert first["job_id"] == "older-job"
    assert newer["job_id"] == "newer-job"
    assert runtime_file.exists()

    updated = job_store.update_job(
        "newer-job",
        current_symbol="BTCUSD",
        progress_pct=55,
        done_batches=1,
        rows_fetched=123,
    )
    assert updated is not None
    assert updated["current_symbol"] == "BTCUSD"
    assert updated["progress_pct"] == 55

    finished = job_store.finish_job(
        "newer-job",
        status="done",
        result={"rows_written": 123},
    )
    assert finished is not None
    assert finished["status"] == "done"
    assert finished["result"] == {"rows_written": 123}
    assert finished["finished_at"] is not None

    jobs = job_store.list_jobs()
    assert [job["job_id"] for job in jobs] == ["newer-job", "older-job"]


def test_active_job_endpoint_returns_running_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The active job endpoint should return the current running job only."""

    monkeypatch.setattr(
        ml_router,
        "load_jobs",
        lambda: [
            {
                "job_id": "done-job",
                "type": "backfill_stocks",
                "asset_class": "stock",
                "symbols": ["AAPL"],
                "status": "done",
                "started_at": "2026-04-20T12:00:00+00:00",
                "finished_at": "2026-04-20T12:01:00+00:00",
                "total_symbols": 1,
                "done_symbols": 1,
                "current_symbol": None,
                "total_batches": 1,
                "done_batches": 1,
                "rows_fetched": 100,
                "current_timeframe": None,
                "status_message": "Completed",
                "progress_pct": 100,
                "error": None,
                "result": {"rows_written": 100},
            },
            {
                "job_id": "running-job",
                "type": "backfill_crypto",
                "asset_class": "crypto",
                "symbols": ["BTC/USD"],
                "status": "running",
                "started_at": "2026-04-20T12:05:00+00:00",
                "finished_at": None,
                "total_symbols": 1,
                "done_symbols": 0,
                "current_symbol": "BTC/USD",
                "total_batches": 1,
                "done_batches": 0,
                "rows_fetched": 0,
                "current_timeframe": "1Day",
                "status_message": "Fetching BTC/USD on 1Day",
                "progress_pct": 0,
                "error": None,
                "result": None,
            },
        ],
    )

    client = TestClient(app)
    response = client.get("/ml/jobs/active")

    assert response.status_code == 200
    assert response.json()["job"]["job_id"] == "running-job"


def test_active_job_endpoint_returns_null_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The active job endpoint should return null when nothing is running."""

    monkeypatch.setattr(ml_router, "load_jobs", lambda: [])

    client = TestClient(app)
    response = client.get("/ml/jobs/active")

    assert response.status_code == 200
    assert response.json() == {"job": None}


@pytest.mark.asyncio
async def test_training_status_cache_reuses_cached_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Training readiness should be served from cache after the first build."""

    from app.ml import training_status_cache

    runtime_dir = tmp_path / ".runtime"
    cache_file = runtime_dir / "ml_training_status.json"
    monkeypatch.setattr(training_status_cache, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(training_status_cache, "_CACHE_PATH", cache_file)

    calls = 0

    async def _builder() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "source": "alpaca_training",
            "total_candles": 10,
            "crypto_candles": 4,
            "stock_candles": 6,
            "crypto_symbols": 1,
            "stock_symbols": 2,
            "symbols_with_data": 3,
            "crypto_detail": [],
            "stock_detail": [],
        }

    first = await training_status_cache.get_or_build_training_status(_builder)
    second = await training_status_cache.get_or_build_training_status(_builder)

    assert calls == 1
    assert first["total_candles"] == 10
    assert second["total_candles"] == 10
    assert second["generated_at"] == first["generated_at"]
    assert cache_file.exists()


def test_job_store_update_persists_slice_b_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry fields should persist alongside the existing job ledger."""

    runtime_dir = tmp_path / ".runtime"
    runtime_file = runtime_dir / "ml_jobs.json"
    monkeypatch.setattr(job_store, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(job_store, "_JOB_STORE_PATH", runtime_file)

    job_store.create_job(
        {
            "job_id": "telemetry-job",
            "type": "backfill_stocks",
            "asset_class": "stock",
            "symbols": ["AAPL"],
            "status": "running",
            "started_at": datetime(2026, 4, 20, 12, 0, tzinfo=UTC).isoformat(),
            "finished_at": None,
            "total_symbols": 1,
            "done_symbols": 0,
            "current_symbol": None,
            "total_batches": 1,
            "done_batches": 0,
            "rows_fetched": 0,
            "current_timeframe": None,
            "status_message": "Queued",
            "progress_pct": 0,
            "error": None,
            "result": None,
        }
    )

    updated = job_store.update_job(
        "telemetry-job",
        current_symbol="AAPL",
        current_timeframe="1Day",
        status_message="Fetching AAPL on 1Day",
        progress_pct=25,
    )

    assert updated is not None
    assert updated["current_timeframe"] == "1Day"
    assert updated["status_message"] == "Fetching AAPL on 1Day"