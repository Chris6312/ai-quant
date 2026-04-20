from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_JOB_STORE_PATH = _RUNTIME_DIR / "ml_jobs.json"

_UNSET = object()


class JobRecord(TypedDict, total=False):
    job_id: str
    type: str
    asset_class: str
    symbols: list[str]
    status: str
    started_at: str
    finished_at: str | None
    total_symbols: int
    done_symbols: int
    current_symbol: str | None
    total_batches: int
    done_batches: int
    rows_fetched: int
    current_timeframe: str | None
    status_message: str | None
    progress_pct: int
    error: str | None
    result: dict[str, object] | None
    gainers_snapshot: list[dict[str, object]]
    created_at: str
    updated_at: str


def _load_jobs_unlocked() -> dict[str, JobRecord]:
    if not _JOB_STORE_PATH.exists():
        return {}
    data = json.loads(_JOB_STORE_PATH.read_text(encoding="utf-8"))
    return cast(dict[str, JobRecord], data)


def _save_jobs_unlocked(jobs: dict[str, JobRecord]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _JOB_STORE_PATH.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def create_job(job: JobRecord) -> JobRecord:
    now = datetime.now(UTC).isoformat()
    record: JobRecord = {
        **job,
        "created_at": job.get("created_at", now),
        "updated_at": now,
    }
    job_id = record["job_id"]
    with _LOCK:
        jobs = _load_jobs_unlocked()
        jobs[job_id] = record
        _save_jobs_unlocked(jobs)
    return record


def update_job(
    job_id: str,
    *,
    type: str | None = None,
    asset_class: str | None = None,
    symbols: list[str] | None = None,
    status: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    total_symbols: int | None = None,
    done_symbols: int | None = None,
    current_symbol: str | None | object = _UNSET,
    total_batches: int | None = None,
    done_batches: int | None = None,
    rows_fetched: int | None = None,
    current_timeframe: str | None | object = _UNSET,
    status_message: str | None | object = _UNSET,
    progress_pct: int | None = None,
    error: str | None | object = _UNSET,
    result: dict[str, object] | None | object = _UNSET,
    gainers_snapshot: list[dict[str, object]] | None = None,
) -> JobRecord | None:
    with _LOCK:
        jobs = _load_jobs_unlocked()
        current = jobs.get(job_id)
        if current is None:
            return None

        if type is not None:
            current["type"] = type
        if asset_class is not None:
            current["asset_class"] = asset_class
        if symbols is not None:
            current["symbols"] = symbols
        if status is not None:
            current["status"] = status
        if started_at is not None:
            current["started_at"] = started_at
        if finished_at is not None:
            current["finished_at"] = finished_at
        if total_symbols is not None:
            current["total_symbols"] = total_symbols
        if done_symbols is not None:
            current["done_symbols"] = done_symbols
        if current_symbol is not _UNSET:
            current["current_symbol"] = cast(str | None, current_symbol)
        if total_batches is not None:
            current["total_batches"] = total_batches
        if done_batches is not None:
            current["done_batches"] = done_batches
        if rows_fetched is not None:
            current["rows_fetched"] = rows_fetched
        if current_timeframe is not _UNSET:
            current["current_timeframe"] = cast(str | None, current_timeframe)
        if status_message is not _UNSET:
            current["status_message"] = cast(str | None, status_message)
        if progress_pct is not None:
            current["progress_pct"] = progress_pct

        if error is not _UNSET:
            current["error"] = cast(str | None, error)
        if result is not _UNSET:
            current["result"] = cast(dict[str, object] | None, result)
        if gainers_snapshot is not None:
            current["gainers_snapshot"] = gainers_snapshot
        current["updated_at"] = datetime.now(UTC).isoformat()

        _save_jobs_unlocked(jobs)
        return current


def finish_job(
    job_id: str,
    *,
    status: str,
    error: str | None = None,
    result: dict[str, object] | None = None,
) -> JobRecord | None:
    return update_job(
        job_id,
        status=status,
        finished_at=datetime.now(UTC).isoformat(),
        error=error,
        result=result,
    )


def get_job(job_id: str) -> JobRecord | None:
    with _LOCK:
        return _load_jobs_unlocked().get(job_id)


def list_jobs() -> list[JobRecord]:
    with _LOCK:
        jobs = _load_jobs_unlocked()
    return sorted(
        jobs.values(),
        key=lambda job: job.get("started_at", ""),
        reverse=True,
    )
