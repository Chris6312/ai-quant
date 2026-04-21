"""Health and observability helpers for managed candle workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import (
    WorkerHealth,
    WorkerLifecycleEvent,
    WorkerSnapshot,
)


@dataclass(frozen=True, slots=True)
class WorkerHealthSnapshot:
    """Aggregated runtime view used by the runtime API."""

    as_of: datetime
    total_workers: int
    healthy_workers: int
    stale_workers: int
    inactive_workers: int
    error_workers: int
    workers: list[WorkerSnapshot]
    recent_events: list[WorkerLifecycleEvent]


class WorkerHealthService:
    """Build runtime health summaries from the worker registry."""

    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry

    def snapshot(self, event_limit: int = 20) -> WorkerHealthSnapshot:
        """Return a summarized runtime view for managed workers."""

        workers = self._registry.list_snapshots()
        recent_events = self._registry.list_events()[-event_limit:]
        healthy_workers = 0
        stale_workers = 0
        inactive_workers = 0
        error_workers = 0

        for worker in workers:
            if worker.health is WorkerHealth.HEALTHY:
                healthy_workers += 1
            elif worker.health is WorkerHealth.STALE:
                stale_workers += 1
            elif worker.health is WorkerHealth.INACTIVE:
                inactive_workers += 1
            elif worker.health is WorkerHealth.ERROR:
                error_workers += 1

        return WorkerHealthSnapshot(
            as_of=datetime.now(tz=UTC),
            total_workers=len(workers),
            healthy_workers=healthy_workers,
            stale_workers=stale_workers,
            inactive_workers=inactive_workers,
            error_workers=error_workers,
            workers=workers,
            recent_events=recent_events,
        )