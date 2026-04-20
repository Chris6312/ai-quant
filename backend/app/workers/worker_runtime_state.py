"""Worker runtime state models for Phase 4 orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class WorkerStatus(StrEnum):
    """Lifecycle status for a managed candle worker."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class WorkerHealth(StrEnum):
    """Health classification derived from registry timestamps and status."""

    HEALTHY = "healthy"
    STALE = "stale"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WorkerKey:
    """Unique identifier for one managed worker."""

    symbol: str
    asset_class: str
    timeframe: str

    @property
    def id(self) -> str:
        """Return the stable worker identifier."""

        return f"{self.asset_class}:{self.symbol}:{self.timeframe}"


@dataclass(frozen=True, slots=True)
class WorkerLifecycleEvent:
    """One point-in-time registry event for observability."""

    worker_id: str
    status: WorkerStatus
    recorded_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerSnapshot:
    """Immutable view of a worker's runtime state."""

    key: WorkerKey
    source: str
    status: WorkerStatus
    started_at: datetime
    updated_at: datetime
    last_heartbeat_at: datetime | None
    last_candle_close_at: datetime | None
    last_error: str | None
    task_name: str | None
    heartbeat_ttl_s: int

    @property
    def heartbeat_age_s(self) -> float | None:
        """Return the age of the latest heartbeat in seconds."""

        if self.last_heartbeat_at is None:
            return None
        return (datetime.now(tz=UTC) - self.last_heartbeat_at).total_seconds()

    @property
    def health(self) -> WorkerHealth:
        """Return the derived health status for the worker."""

        if self.status is WorkerStatus.ERROR:
            return WorkerHealth.ERROR
        if self.status in {WorkerStatus.STOPPED, WorkerStatus.STOPPING}:
            return WorkerHealth.INACTIVE
        if self.last_heartbeat_at is None:
            return WorkerHealth.STALE
        if self.heartbeat_age_s is not None and self.heartbeat_age_s > self.heartbeat_ttl_s:
            return WorkerHealth.STALE
        return WorkerHealth.HEALTHY
