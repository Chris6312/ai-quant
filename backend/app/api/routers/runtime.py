"""Runtime visibility endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.config.constants import (
    ML_CRYPTO_INTRADAY_WORKER_ID,
    ML_CRYPTO_INTRADAY_WORKER_SOURCE,
)
from app.config.crypto_scope import list_crypto_universe_symbols, list_crypto_watchlist_symbols
from app.ml.freshness import (
    classify_ml_freshness,
    evaluate_crypto_ml_freshness,
    ml_candle_date,
)
from app.repositories.watchlist import WatchlistRepository
from app.runtime_events import RuntimeTaskEvent, list_runtime_task_events
from app.services.crypto_runtime_targets import list_crypto_runtime_targets
from app.workers.worker_health_service import WorkerHealthService
from app.workers.worker_runtime_state import (
    WorkerKey,
    WorkerLifecycleEvent,
    WorkerSnapshot,
    WorkerStatus,
)
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
    snapshot = service.snapshot(event_limit=max(event_limit, 100))
    supervisor = _get_worker_supervisor(request).snapshot()
    ml_freshness = await _serialize_ml_freshness(session)
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
            "scope_note": "Stock watchlist coverage is separate from crypto scope coverage.",
        },
        "crypto_scope": _serialize_crypto_scope(snapshot.workers),
        "workers": workers,
        "ml_workers": _serialize_ml_workers(snapshot.workers, ml_freshness),
        "watchlist_targets": targets,
        "recent_events": _serialize_recent_events(
            worker_events=snapshot.recent_events,
            task_events=list_runtime_task_events(limit=100),
            event_limit=event_limit,
        ),
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


def _serialize_recent_events(
    *,
    worker_events: list[WorkerLifecycleEvent],
    task_events: list[RuntimeTaskEvent],
    event_limit: int,
) -> list[dict[str, Any]]:
    """Merge in-process worker events with shared Celery task events."""

    if event_limit <= 0:
        return []

    events: list[WorkerLifecycleEvent | RuntimeTaskEvent] = [
        *worker_events,
        *task_events,
    ]
    events.sort(key=lambda event: event.recorded_at)
    return [_serialize_event(event) for event in events[-event_limit:]]

def _serialize_crypto_scope(workers: list[WorkerSnapshot]) -> dict[str, Any]:
    """Return the current crypto universe, watchlist, and active runtime scope."""

    universe_symbols = list_crypto_universe_symbols()
    watchlist_symbols = list_crypto_watchlist_symbols()
    crypto_targets = list_crypto_runtime_targets()
    active_runtime_symbols = sorted(
        {
            worker.key.symbol
            for worker in workers
            if worker.key.asset_class == "crypto"
            and worker.status in {WorkerStatus.STARTING, WorkerStatus.RUNNING}
        }
    )
    return {
        "universe_symbols": universe_symbols,
        "universe_count": len(universe_symbols),
        "universe_source": "KRAKEN_UNIVERSE",
        "watchlist_symbols": watchlist_symbols,
        "watchlist_count": len(watchlist_symbols),
        "watchlist_source": "crypto universe",
        "target_runtime_symbols": [target.key.symbol for target in crypto_targets],
        "target_runtime_count": len(crypto_targets),
        "target_runtime_source": (
            "derived from crypto watchlist" if crypto_targets else "no crypto targets derived"
        ),
        "active_runtime_symbols": active_runtime_symbols,
        "active_runtime_count": len(active_runtime_symbols),
        "active_runtime_source": (
            "attached crypto candle scheduler"
            if active_runtime_symbols
            else "no crypto candle scheduler attached yet"
        ),
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


async def _serialize_ml_freshness(session: AsyncSession) -> dict[str, Any]:
    """Return ML-lane candle freshness for the active crypto ML universe."""

    return (await evaluate_crypto_ml_freshness(session)).to_api_payload()


def _classify_ml_freshness(
    latest_candle_at: datetime | None,
    *,
    has_missing_or_stale_symbols: bool = False,
    current_date: date | None = None,
) -> str:
    """Backward-compatible wrapper around the shared ML freshness classifier."""

    return classify_ml_freshness(
        latest_candle_at,
        has_missing_or_stale_symbols=has_missing_or_stale_symbols,
        current_date=current_date,
    )


def _serialize_ml_workers(
    workers: list[WorkerSnapshot],
    ml_freshness: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return configured ML worker visibility without mixing it into candle workers."""

    existing = next(
        (worker for worker in workers if worker.key.id == ML_CRYPTO_INTRADAY_WORKER_ID),
        None,
    )
    if existing is not None:
        worker_payload = _serialize_worker(existing)
        worker_payload.update(ml_freshness)
        worker_payload["health"] = ml_freshness["freshness"]
        return [worker_payload]

    now = datetime.now(tz=UTC).isoformat()
    return [
        {
            "worker_id": ML_CRYPTO_INTRADAY_WORKER_ID,
            "symbol": "crypto",
            "asset_class": "ml",
            "timeframe": "15m/1h/4h",
            "source": ML_CRYPTO_INTRADAY_WORKER_SOURCE,
            "status": "configured",
            "health": ml_freshness["freshness"],
            "started_at": now,
            "updated_at": now,
            "last_heartbeat_at": None,
            "last_candle_close_at": ml_freshness["latest_ml_candle_at"],
            "last_error": None,
            "task_name": "tasks.ml_candles.crypto_intraday_sync",
            "heartbeat_ttl_s": 0,
            "heartbeat_age_s": None,
            **ml_freshness,
        }
    ]


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


def _serialize_event(
    event: WorkerLifecycleEvent | RuntimeTaskEvent,
) -> dict[str, Any]:
    """Convert a lifecycle event to an API payload."""

    status = event.status.value if isinstance(event.status, WorkerStatus) else event.status
    return {
        "worker_id": event.worker_id,
        "status": status,
        "recorded_at": event.recorded_at.isoformat(),
        "detail": event.detail,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    """Serialize an optional datetime to an ISO 8601 string."""

    return value.isoformat() if value is not None else None


def _serialize_date(value: datetime | None) -> str | None:
    """Serialize an optional datetime as an ISO date."""

    ml_date = ml_candle_date(value)
    return ml_date.isoformat() if ml_date is not None else None


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
