"""In-memory registry for managed candle workers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.config.constants import CANDLE_HEARTBEAT_TTL_SECONDS
from app.workers.worker_runtime_state import (
    WorkerKey,
    WorkerLifecycleEvent,
    WorkerSnapshot,
    WorkerStatus,
)


@dataclass(slots=True)
class _WorkerEntry:
    """Mutable registry entry stored internally."""

    snapshot: WorkerSnapshot
    task_ref: object | None


class WorkerRegistry:
    """Track active worker runtime metadata for orchestration and health checks."""

    def __init__(
        self,
        heartbeat_ttl_s: int = CANDLE_HEARTBEAT_TTL_SECONDS,
        max_events: int = 250,
    ) -> None:
        self.heartbeat_ttl_s = heartbeat_ttl_s
        self.max_events = max_events
        self._workers: dict[str, _WorkerEntry] = {}
        self._events: list[WorkerLifecycleEvent] = []

    def register(
        self,
        key: WorkerKey,
        source: str,
        *,
        task_ref: object | None = None,
        task_name: str | None = None,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Register a worker as starting or refresh its task metadata."""

        now = recorded_at or datetime.now(tz=UTC)
        existing = self._workers.get(key.id)
        if existing is None:
            snapshot = WorkerSnapshot(
                key=key,
                source=source,
                status=WorkerStatus.STARTING,
                started_at=now,
                updated_at=now,
                last_heartbeat_at=None,
                last_candle_close_at=None,
                last_error=None,
                task_name=task_name,
                heartbeat_ttl_s=self.heartbeat_ttl_s,
            )
        else:
            snapshot = replace(
                existing.snapshot,
                source=source,
                status=WorkerStatus.STARTING,
                updated_at=now,
                task_name=task_name,
                last_error=None,
            )
        self._workers[key.id] = _WorkerEntry(snapshot=snapshot, task_ref=task_ref)
        self._record_event(key.id, WorkerStatus.STARTING, now)
        return snapshot

    def mark_running(
        self,
        key: WorkerKey,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Mark a registered worker as actively running."""

        return self._update_status(
            key,
            WorkerStatus.RUNNING,
            recorded_at=recorded_at,
        )

    def mark_heartbeat(
        self,
        key: WorkerKey,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Update the worker heartbeat timestamp and ensure it is running."""

        entry = self._require_entry(key)
        now = recorded_at or datetime.now(tz=UTC)
        snapshot = replace(
            entry.snapshot,
            status=WorkerStatus.RUNNING,
            updated_at=now,
            last_heartbeat_at=now,
        )
        entry.snapshot = snapshot
        self._record_event(
            key.id,
            WorkerStatus.RUNNING,
            now,
            detail="heartbeat",
        )
        return snapshot

    def mark_candle_close(
        self,
        key: WorkerKey,
        candle_close_at: datetime,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Update the latest observed candle close time for the worker."""

        entry = self._require_entry(key)
        now = recorded_at or datetime.now(tz=UTC)
        snapshot = replace(
            entry.snapshot,
            status=WorkerStatus.RUNNING,
            updated_at=now,
            last_candle_close_at=candle_close_at,
        )
        entry.snapshot = snapshot
        return snapshot

    def mark_stopping(
        self,
        key: WorkerKey,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Mark a worker as shutting down."""

        return self._update_status(
            key,
            WorkerStatus.STOPPING,
            recorded_at=recorded_at,
        )

    def mark_stopped(
        self,
        key: WorkerKey,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Mark a worker as stopped while retaining the latest snapshot."""

        return self._update_status(
            key,
            WorkerStatus.STOPPED,
            recorded_at=recorded_at,
        )

    def mark_error(
        self,
        key: WorkerKey,
        message: str,
        *,
        recorded_at: datetime | None = None,
    ) -> WorkerSnapshot:
        """Record a worker error and transition it into error state."""

        entry = self._require_entry(key)
        now = recorded_at or datetime.now(tz=UTC)
        snapshot = replace(
            entry.snapshot,
            status=WorkerStatus.ERROR,
            updated_at=now,
            last_error=message,
        )
        entry.snapshot = snapshot
        self._record_event(key.id, WorkerStatus.ERROR, now, detail=message)
        return snapshot

    def remove(self, key: WorkerKey) -> None:
        """Remove a worker from the live registry."""

        self._workers.pop(key.id, None)

    def get(self, key: WorkerKey) -> WorkerSnapshot | None:
        """Return the worker snapshot when present."""

        entry = self._workers.get(key.id)
        return None if entry is None else entry.snapshot

    def get_task_ref(self, key: WorkerKey) -> object | None:
        """Return the stored task reference for a worker."""

        entry = self._workers.get(key.id)
        return None if entry is None else entry.task_ref

    def list_snapshots(self) -> list[WorkerSnapshot]:
        """Return all worker snapshots in stable order."""

        snapshots = [entry.snapshot for entry in self._workers.values()]
        return sorted(
            snapshots,
            key=lambda item: (
                item.key.asset_class,
                item.key.symbol,
                item.key.timeframe,
            ),
        )

    def list_events(self) -> list[WorkerLifecycleEvent]:
        """Return the retained lifecycle events."""

        return list(self._events)

    def _update_status(
        self,
        key: WorkerKey,
        status: WorkerStatus,
        *,
        recorded_at: datetime | None,
    ) -> WorkerSnapshot:
        entry = self._require_entry(key)
        now = recorded_at or datetime.now(tz=UTC)
        snapshot = replace(
            entry.snapshot,
            status=status,
            updated_at=now,
        )
        entry.snapshot = snapshot
        self._record_event(key.id, status, now)
        return snapshot

    def _record_event(
        self,
        worker_id: str,
        status: WorkerStatus,
        recorded_at: datetime,
        detail: str | None = None,
    ) -> None:
        self._events.append(
            WorkerLifecycleEvent(
                worker_id=worker_id,
                status=status,
                recorded_at=recorded_at,
                detail=detail,
            )
        )
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events :]

    def _require_entry(self, key: WorkerKey) -> _WorkerEntry:
        entry = self._workers.get(key.id)
        if entry is None:
            raise KeyError(f"Worker is not registered: {key.id}")
        return entry