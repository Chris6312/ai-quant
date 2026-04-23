from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_JOB_STORE_PATH = _RUNTIME_DIR / "ml_jobs.json"

_UNSET = object()

_STALE_JOB_AFTER = timedelta(minutes=5)


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
    heartbeat_at: str | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _load_jobs_unlocked() -> dict[str, JobRecord]:
    if not _JOB_STORE_PATH.exists():
        return {}
    data = json.loads(_JOB_STORE_PATH.read_text(encoding="utf-8"))
    return cast(dict[str, JobRecord], data)


def _save_jobs_unlocked(jobs: dict[str, JobRecord]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _JOB_STORE_PATH.write_text(
        json.dumps(jobs, indent=2),
        encoding="utf-8",
    )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _clamp_progress(value: int) -> int:
    if value < 0:
        return 0
    if value > 100:
        return 100
    return value


def _derive_progress(
    current: JobRecord,
    *,
    explicit_progress_pct: int | None,
    status: str | None,
    total_symbols: int | None,
    done_symbols: int | None,
    total_batches: int | None,
    done_batches: int | None,
) -> int:
    if explicit_progress_pct is not None:
        return _clamp_progress(explicit_progress_pct)

    resolved_status = status if status is not None else current.get("status")
    if resolved_status in {"done", "completed", "success"}:
        return 100
    if resolved_status in {"error", "failed", "cancelled"}:
        current_progress = current.get("progress_pct", 0)
        if isinstance(current_progress, int):
            return _clamp_progress(current_progress)
        return 0

    resolved_total_symbols = (
        total_symbols if total_symbols is not None else current.get("total_symbols")
    )
    resolved_done_symbols = (
        done_symbols if done_symbols is not None else current.get("done_symbols")
    )
    if isinstance(resolved_total_symbols, int) and resolved_total_symbols > 0:
        done_count = resolved_done_symbols if isinstance(resolved_done_symbols, int) else 0
        return _clamp_progress(round((done_count / resolved_total_symbols) * 100))

    resolved_total_batches = (
        total_batches if total_batches is not None else current.get("total_batches")
    )
    resolved_done_batches = (
        done_batches if done_batches is not None else current.get("done_batches")
    )
    if isinstance(resolved_total_batches, int) and resolved_total_batches > 0:
        done_count = resolved_done_batches if isinstance(resolved_done_batches, int) else 0
        return _clamp_progress(round((done_count / resolved_total_batches) * 100))

    current_progress = current.get("progress_pct", 0)
    if isinstance(current_progress, int):
        return _clamp_progress(current_progress)
    return 0


def _is_running_status(status: object) -> bool:
    return status in {"pending", "queued", "running"}


def _mark_job_stale(job: JobRecord) -> None:
    now_iso = _utc_now_iso()
    previous_status = str(job.get("status") or "running")
    status_message = job.get("status_message")
    base_message = (
        str(status_message)
        if isinstance(status_message, str) and status_message
        else "Job became stale with no heartbeat updates"
    )
    job["status"] = "failed"
    job["finished_at"] = now_iso
    job["updated_at"] = now_iso
    job["heartbeat_at"] = None
    job["error"] = f"stale job auto-recovered from status={previous_status}"
    job["status_message"] = f"{base_message} [auto-recovered stale job]"
    if not isinstance(job.get("progress_pct"), int):
        job["progress_pct"] = 0


def _reconcile_jobs_unlocked(jobs: dict[str, JobRecord]) -> bool:
    changed = False
    now = _utc_now()

    for job in jobs.values():
        status = job.get("status")
        if not _is_running_status(status):
            continue

        heartbeat_dt = _parse_datetime(job.get("heartbeat_at"))
        updated_dt = _parse_datetime(job.get("updated_at"))
        reference_dt = heartbeat_dt or updated_dt

        if reference_dt is None:
            _mark_job_stale(job)
            changed = True
            continue

        if now - reference_dt > _STALE_JOB_AFTER:
            _mark_job_stale(job)
            changed = True

    return changed


def create_job(job: JobRecord) -> JobRecord:
    now_iso = _utc_now_iso()
    record: JobRecord = {
        **job,
        "created_at": job.get("created_at", now_iso),
        "updated_at": now_iso,
    }

    status = record.get("status")
    if _is_running_status(status):
        record["heartbeat_at"] = now_iso
    else:
        heartbeat_value = record.get("heartbeat_at")
        record["heartbeat_at"] = heartbeat_value if isinstance(heartbeat_value, str) else None

    progress_pct = record.get("progress_pct")
    if isinstance(progress_pct, int):
        record["progress_pct"] = _clamp_progress(progress_pct)
    elif status in {"done", "completed", "success"}:
        record["progress_pct"] = 100
    else:
        record["progress_pct"] = 0

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
        if error is not _UNSET:
            current["error"] = cast(str | None, error)
        if result is not _UNSET:
            current["result"] = cast(dict[str, object] | None, result)
        if gainers_snapshot is not None:
            current["gainers_snapshot"] = gainers_snapshot

        resolved_progress = _derive_progress(
            current,
            explicit_progress_pct=progress_pct,
            status=status,
            total_symbols=total_symbols,
            done_symbols=done_symbols,
            total_batches=total_batches,
            done_batches=done_batches,
        )
        current["progress_pct"] = resolved_progress

        now_iso = _utc_now_iso()
        current["updated_at"] = now_iso

        resolved_status = current.get("status")
        if _is_running_status(resolved_status):
            current["heartbeat_at"] = now_iso
            if current.get("finished_at") is not None:
                current["finished_at"] = None
        else:
            current["heartbeat_at"] = None
            if resolved_status in {"done", "completed", "success"}:
                current["progress_pct"] = 100
                if current.get("finished_at") is None:
                    current["finished_at"] = now_iso

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
        finished_at=_utc_now_iso(),
        progress_pct=100 if status in {"done", "completed", "success"} else None,
        error=error,
        result=result,
    )


def get_job(job_id: str) -> JobRecord | None:
    with _LOCK:
        jobs = _load_jobs_unlocked()
        changed = _reconcile_jobs_unlocked(jobs)
        if changed:
            _save_jobs_unlocked(jobs)
        return jobs.get(job_id)


def list_jobs() -> list[JobRecord]:
    with _LOCK:
        jobs = _load_jobs_unlocked()
        changed = _reconcile_jobs_unlocked(jobs)
        if changed:
            _save_jobs_unlocked(jobs)

    return sorted(
        jobs.values(),
        key=lambda job: str(job.get("started_at", "")),
        reverse=True,
    )