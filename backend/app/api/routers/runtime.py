"""Runtime visibility endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.repositories.watchlist import WatchlistRepository
from app.workers.worker_health_service import WorkerHealthService
from app.workers.worker_runtime_state import WorkerKey, WorkerLifecycleEvent, WorkerSnapshot
from app.workers.worker_supervisor import WorkerSupervisor

router = APIRouter(prefix="/runtime", tags=["runtime"])


class _RuntimeAppStateProtocol(Protocol):
    """Typed view of runtime services stored on FastAPI app.state."""

    worker_health_service: WorkerHealthService
    worker_supervisor: WorkerSupervisor


def _get_worker_health_service(request: Request) -> WorkerHealthService:
    """Return the shared worker health service stored on the app state."""

    state = cast(_RuntimeAppStateProtocol, request.app.state)
    return state.worker_health_service


def _get_worker_supervisor(request: Request) -> WorkerSupervisor:
    """Return the shared worker supervisor stored on the app state."""

    state = cast(_RuntimeAppStateProtocol, request.app.state)
    return state.worker_supervisor


@router.get("/workers")
async def get_runtime_workers(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    event_limit: int = Query(default=20, ge=0, le=100),
) -> dict[str, Any]:
    """Return the current managed worker health snapshot plus watchlist coverage."""

    service = _get_worker_health_service(request)
    snapshot = service.snapshot(event_limit=event_limit)
    supervisor = _get_worker_supervisor(request).snapshot()
    workers = [_serialize_worker(worker) for worker in snapshot.workers]
    targets = await _serialize_watchlist_targets(session, snapshot.workers)
    attached_workers = sum(1 for target in targets if target["worker_attached"])
    unattached_workers = len(targets) - attached_workers

    return {
        "as_of": snapshot.as_of.isoformat(),
        "summary": {
            "total_workers": snapshot.total_workers,
            "healthy_workers": snapshot.healthy_workers,
            "stale_workers": snapshot.stale_workers,
            "inactive_workers": snapshot.inactive_workers,
            "error_workers": snapshot.error_workers,
        },
        "coverage": {
            "watchlist_targets": len(targets),
            "attached_workers": attached_workers,
            "unattached_workers": unattached_workers,
        },
        "workers": workers,
        "watchlist_targets": targets,
        "recent_events": [_serialize_event(event) for event in snapshot.recent_events],
        "supervisor": {
            "name": supervisor.name,
            "interval_seconds": supervisor.interval_seconds,
            "enabled": supervisor.enabled,
            "running": supervisor.running,
            "iteration_count": supervisor.iteration_count,
            "last_started_at": _serialize_datetime(supervisor.last_started_at),
            "last_finished_at": _serialize_datetime(supervisor.last_finished_at),
            "last_success_at": _serialize_datetime(supervisor.last_success_at),
            "last_error": supervisor.last_error,
            "last_result": _serialize_sync_result(supervisor.last_result),
        },
    }


async def _serialize_watchlist_targets(
    session: AsyncSession,
    workers: list[WorkerSnapshot],
) -> list[dict[str, Any]]:
    """Return active stock-watchlist targets and whether workers are attached."""

    repository = WatchlistRepository(session)
    rows = await repository.list_active()
    workers_by_id = {worker.key.id: worker for worker in workers}
    targets: list[dict[str, Any]] = []

    for row in rows:
        if row.asset_class.lower() != "stock":
            continue
        key = WorkerKey(symbol=row.symbol.upper(), asset_class="stock", timeframe="1Day")
        worker = workers_by_id.get(key.id)
        targets.append(
            {
                "worker_id": key.id,
                "symbol": key.symbol,
                "asset_class": key.asset_class,
                "timeframe": key.timeframe,
                "worker_attached": worker is not None,
                "worker_status": worker.status.value if worker is not None else None,
                "worker_health": worker.health.value if worker is not None else None,
                "last_heartbeat_at": _serialize_datetime(
                    worker.last_heartbeat_at if worker is not None else None
                ),
                "last_error": worker.last_error if worker is not None else None,
            }
        )

    return targets


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


def _serialize_sync_result(value: object) -> dict[str, int] | None:
    """Serialize the last sync result when present."""

    if value is None:
        return None
    started = cast(Any, value).started
    stopped = cast(Any, value).stopped
    unchanged = cast(Any, value).unchanged
    return {
        "started": int(started),
        "stopped": int(stopped),
        "unchanged": int(unchanged),
    }