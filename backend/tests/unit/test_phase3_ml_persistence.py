"""Phase 3 ML persistence tests."""

from __future__ import annotations

import asyncio
from collections import namedtuple
from datetime import UTC, datetime, timedelta
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
            "source": "alpaca_training,crypto_csv_training",
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
    assert second["cache_state"] == "fresh"
    assert cache_file.exists()


@pytest.mark.asyncio
async def test_training_status_cache_rebuilds_when_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expired readiness cache should rebuild instead of serving old data."""

    from app.ml import training_status_cache

    runtime_dir = tmp_path / ".runtime"
    cache_file = runtime_dir / "ml_training_status.json"
    monkeypatch.setattr(training_status_cache, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(training_status_cache, "_CACHE_PATH", cache_file)

    stale_generated_at = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        (
            "{\n"
            '  "source": "alpaca_training",\n'
            '  "total_candles": 1,\n'
            '  "crypto_candles": 0,\n'
            '  "stock_candles": 1,\n'
            '  "crypto_symbols": 0,\n'
            '  "stock_symbols": 1,\n'
            '  "symbols_with_data": 1,\n'
            '  "crypto_detail": [],\n'
            '  "stock_detail": [],\n'
            f'  "generated_at": "{stale_generated_at}",\n'
            '  "cache_state": "fresh",\n'
            '  "schema_version": 2,\n'
            '  "invalidated_at": null,\n'
            '  "invalidation_reason": null\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    async def _builder() -> dict[str, object]:
        return {
            "source": "alpaca_training,crypto_csv_training",
            "total_candles": 99,
            "crypto_candles": 40,
            "stock_candles": 59,
            "crypto_symbols": 2,
            "stock_symbols": 3,
            "symbols_with_data": 5,
            "crypto_detail": [],
            "stock_detail": [],
        }

    rebuilt = await training_status_cache.get_or_build_training_status(_builder)

    assert rebuilt["total_candles"] == 99
    assert rebuilt["cache_state"] == "fresh"
    assert rebuilt["generated_at"] != stale_generated_at


@pytest.mark.asyncio
async def test_training_status_cache_marks_existing_snapshot_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingestion start should mark the readiness cache stale instead of deleting it."""

    from app.ml import training_status_cache

    runtime_dir = tmp_path / ".runtime"
    cache_file = runtime_dir / "ml_training_status.json"
    monkeypatch.setattr(training_status_cache, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(training_status_cache, "_CACHE_PATH", cache_file)

    async def _builder() -> dict[str, object]:
        return {
            "source": "alpaca_training",
            "total_candles": 10,
            "crypto_candles": 0,
            "stock_candles": 10,
            "crypto_symbols": 0,
            "stock_symbols": 1,
            "symbols_with_data": 1,
            "crypto_detail": [],
            "stock_detail": [],
        }

    first = await training_status_cache.rebuild_training_status(_builder)
    stale = training_status_cache.mark_training_status_stale("stock_backfill_started")

    assert stale is not None
    assert stale["cache_state"] == "stale"
    assert stale["generated_at"] == first["generated_at"]
    assert stale["invalidation_reason"] == "stock_backfill_started"
    assert stale["invalidated_at"] is not None


@pytest.mark.asyncio
async def test_training_status_cache_discards_corrupt_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corrupt readiness cache files should be ignored and replaced cleanly."""

    from app.ml import training_status_cache

    runtime_dir = tmp_path / ".runtime"
    cache_file = runtime_dir / "ml_training_status.json"
    monkeypatch.setattr(training_status_cache, "_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(training_status_cache, "_CACHE_PATH", cache_file)

    runtime_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("not-json", encoding="utf-8")

    async def _builder() -> dict[str, object]:
        return {
            "source": "alpaca_training",
            "total_candles": 7,
            "crypto_candles": 2,
            "stock_candles": 5,
            "crypto_symbols": 1,
            "stock_symbols": 1,
            "symbols_with_data": 2,
            "crypto_detail": [],
            "stock_detail": [],
        }

    rebuilt = await training_status_cache.get_or_build_training_status(_builder)

    assert rebuilt["total_candles"] == 7
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


def test_build_training_status_splits_crypto_and_stock_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Training readiness should expose grouped detail for both asset classes."""

    Row = namedtuple(
        "Row",
        ["symbol", "asset_class", "timeframe", "row_count", "earliest", "latest"],
    )

    rows = [
        Row(
            symbol="BTC/USD",
            asset_class="crypto",
            timeframe="1Day",
            row_count=10,
            earliest=datetime(2026, 1, 1, tzinfo=UTC),
            latest=datetime(2026, 1, 10, tzinfo=UTC),
        ),
        Row(
            symbol="AAPL",
            asset_class="stock",
            timeframe="1Day",
            row_count=20,
            earliest=datetime(2026, 2, 1, tzinfo=UTC),
            latest=datetime(2026, 2, 20, tzinfo=UTC),
        ),
    ]

    class _FakeResult:
        def all(self) -> list[object]:
            return list(rows)

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def _fake_session_factory() -> _FakeSession:
        return _FakeSession()

    async def _fake_stmt(session: object) -> _FakeResult:
        return _FakeResult()

    monkeypatch.setattr(ml_router, "get_settings", lambda: object())
    monkeypatch.setattr(ml_router, "build_engine", lambda settings: object())
    monkeypatch.setattr(ml_router, "build_session_factory", lambda engine: _fake_session_factory)
    monkeypatch.setattr(ml_router, "_training_status_stmt", _fake_stmt)

    status = asyncio.run(ml_router._build_training_status())

    assert status["total_candles"] == 30
    assert status["crypto_candles"] == 10
    assert status["stock_candles"] == 20
    assert status["crypto_symbols"] == 1
    assert status["stock_symbols"] == 1
    assert status["symbols_with_data"] == 2
    assert status["crypto_detail"][0]["symbol"] == "BTC/USD"
    assert status["crypto_detail"][0]["candle_count"] == 10
    assert status["stock_detail"][0]["symbol"] == "AAPL"
