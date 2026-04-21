"""Runtime visibility endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, cast

from fastapi import APIRouter, Query, Request

from app.workers.worker_health_service import WorkerHealthService
from app.workers.worker_runtime_state import WorkerLifecycleEvent, WorkerSnapshot

router = APIRouter(prefix="/runtime", tags=["runtime"])


class _RuntimeAppStateProtocol(Protocol):
    """Typed view of runtime services stored on FastAPI app.state."""

    worker_health_service: WorkerHealthService


def _get_worker_health_service(request: Request) -> WorkerHealthService:
    """Return the shared worker health service stored on the app state."""
    state = cast(_RuntimeAppStateProtocol, request.app.state)
    return state.worker_health_service


@router.get("/workers")
def get_runtime_workers(
    request: Request,
    event_limit: int = Query(default=20, ge=0, le=100),
) -> dict[str, Any]:
    """Return the current managed worker health snapshot."""
    service = _get_worker_health_service(request)
    snapshot = service.snapshot(event_limit=event_limit)
    return {
        "as_of": snapshot.as_of.isoformat(),
        "summary": {
            "total_workers": snapshot.total_workers,
            "healthy_workers": snapshot.healthy_workers,
            "stale_workers": snapshot.stale_workers,
            "inactive_workers": snapshot.inactive_workers,
            "error_workers": snapshot.error_workers,
        },
        "workers": [_serialize_worker(worker) for worker in snapshot.workers],
        "recent_events": [_serialize_event(event) for event in snapshot.recent_events],
    }


def _serialize_worker(worker: WorkerSnapshot) -> dict[str, Any]:
    """Convert a worker snapshot to an API payload."""
    return {
        "worker_id": worker.key.id,
        "symbol": worker.key.symbol,
        "asset_class": worker.key.asset_class,
        "timeframe": worker.key.timeframe,
        "source": worker.source,
        "status": worker.status.value,
        "health": worker.health.value,
        "started_at": worker.started_at.isoformat(),
        "updated_at": worker.updated_at.isoformat(),
        "last_heartbeat_at": _serialize_datetime(worker.last_heartbeat_at),
        "last_candle_close_at": _serialize_datetime(worker.last_candle_close_at),
        "last_error": worker.last_error,
        "task_name": worker.task_name,
        "heartbeat_ttl_s": worker.heartbeat_ttl_s,
        "heartbeat_age_s": worker.heartbeat_age_s,
    }


def _serialize_event(event: WorkerLifecycleEvent) -> dict[str, Any]:
    """Convert a lifecycle event to an API payload."""
    return {
        "worker_id": event.worker_id,
        "status": event.status.value,
        "recorded_at": event.recorded_at.isoformat(),
        "detail": event.detail,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    """Serialize an optional datetime to an ISO 8601 string."""
    return value.isoformat() if value is not None else None