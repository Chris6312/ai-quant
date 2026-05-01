"""Shared runtime event log for cross-process task visibility."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_RUNTIME_DIR = Path(".runtime")
_RUNTIME_EVENT_PATH = _RUNTIME_DIR / "runtime_task_events.json"
_MAX_RUNTIME_EVENTS = 250
_ALLOWED_STATUSES = {"starting", "running", "stopping", "stopped", "error"}


@dataclass(frozen=True, slots=True)
class RuntimeTaskEvent:
    """One task lifecycle event shared between Celery workers and the API."""

    worker_id: str
    status: str
    recorded_at: datetime
    detail: str | None = None


def record_runtime_task_event(
    *,
    worker_id: str,
    status: str,
    detail: str | None = None,
    recorded_at: datetime | None = None,
) -> None:
    """Append a runtime task event to the shared file-backed event log."""

    normalized_status = status.lower()
    if normalized_status not in _ALLOWED_STATUSES:
        raise ValueError(f"Unsupported runtime task status: {status}")

    event = RuntimeTaskEvent(
        worker_id=worker_id,
        status=normalized_status,
        recorded_at=recorded_at or datetime.now(tz=UTC),
        detail=detail,
    )
    events = list_runtime_task_events(limit=_MAX_RUNTIME_EVENTS)
    events.append(event)
    _write_events(events[-_MAX_RUNTIME_EVENTS:])


def list_runtime_task_events(limit: int = 20) -> list[RuntimeTaskEvent]:
    """Return recent shared runtime task events in chronological order."""

    if limit <= 0 or not _RUNTIME_EVENT_PATH.exists():
        return []

    try:
        payload = json.loads(_RUNTIME_EVENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    events: list[RuntimeTaskEvent] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        event = _event_from_payload(item)
        if event is not None:
            events.append(event)

    return events[-limit:]


def _write_events(events: list[RuntimeTaskEvent]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    payload = [_event_to_payload(event) for event in events]
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=_RUNTIME_DIR,
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(_RUNTIME_EVENT_PATH)


def _event_to_payload(event: RuntimeTaskEvent) -> dict[str, str | None]:
    return {
        "worker_id": event.worker_id,
        "status": event.status,
        "recorded_at": event.recorded_at.isoformat(),
        "detail": event.detail,
    }


def _event_from_payload(payload: dict[str, Any]) -> RuntimeTaskEvent | None:
    worker_id = payload.get("worker_id")
    status = payload.get("status")
    recorded_at = payload.get("recorded_at")
    detail = payload.get("detail")
    if not isinstance(worker_id, str):
        return None
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        return None
    if not isinstance(recorded_at, str):
        return None
    if detail is not None and not isinstance(detail, str):
        detail = str(detail)
    try:
        parsed_recorded_at = datetime.fromisoformat(recorded_at)
    except ValueError:
        return None
    if parsed_recorded_at.tzinfo is None:
        parsed_recorded_at = parsed_recorded_at.replace(tzinfo=UTC)
    return RuntimeTaskEvent(
        worker_id=worker_id,
        status=status,
        recorded_at=parsed_recorded_at,
        detail=detail,
    )
