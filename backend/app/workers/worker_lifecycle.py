"""Lifecycle management primitives for Phase 4 candle workers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from app.workers.worker_registry import WorkerRegistry
from app.workers.worker_runtime_state import WorkerKey, WorkerSnapshot, WorkerStatus


class ManagedWorker(Protocol):
    """Protocol for async worker implementations managed by the lifecycle layer."""

    async def run(self) -> None:
        """Run the worker until completion or cancellation."""


@dataclass(frozen=True, slots=True)
class WorkerLaunchSpec:
    """Definition for one managed worker that should be running."""

    key: WorkerKey
    source: str
    worker_factory: Callable[[], ManagedWorker]
    task_name: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerSyncResult:
    """Summary of one desired-state reconciliation pass."""

    started: int
    stopped: int
    unchanged: int


@dataclass(slots=True)
class _ActiveWorker:
    """Internal handle for an active managed worker task."""

    spec: WorkerLaunchSpec
    task: asyncio.Task[None]


class WorkerLifecycleManager:
    """Start, stop, and reconcile managed workers against a desired state."""

    def __init__(self, registry: WorkerRegistry) -> None:
        self._registry = registry
        self._active: dict[str, _ActiveWorker] = {}

    @property
    def active_worker_ids(self) -> set[str]:
        """Return the currently active worker identifiers."""
        return set(self._active)

    def get_task(self, key: WorkerKey) -> asyncio.Task[None] | None:
        """Return the live task for a worker when present."""
        active = self._active.get(key.id)
        return None if active is None else active.task

    def list_active_keys(self) -> list[WorkerKey]:
        """Return active worker keys in stable order."""
        return sorted(
            [active.spec.key for active in self._active.values()],
            key=lambda item: (item.asset_class, item.symbol, item.timeframe),
        )

    async def sync(self, desired_specs: Sequence[WorkerLaunchSpec]) -> WorkerSyncResult:
        """Reconcile active tasks so they match the desired worker set."""
        desired_by_id = {spec.key.id: spec for spec in desired_specs}
        current_ids = set(self._active)
        desired_ids = set(desired_by_id)

        started = 0
        for worker_id in sorted(desired_ids - current_ids):
            await self.start(desired_by_id[worker_id])
            started += 1

        stopped = 0
        for worker_id in sorted(current_ids - desired_ids):
            active = self._active.get(worker_id)
            if active is None:
                continue
            await self.stop(active.spec.key)
            stopped += 1

        unchanged = len(desired_ids & current_ids)
        return WorkerSyncResult(started=started, stopped=stopped, unchanged=unchanged)

    async def start(self, spec: WorkerLaunchSpec) -> WorkerSnapshot:
        """Start one managed worker if it is not already active."""
        existing = self._active.get(spec.key.id)
        if existing is not None:
            snapshot = self._registry.get(spec.key)
            if snapshot is None:
                raise RuntimeError(
                    f"Registry entry missing for active worker: {spec.key.id}"
                )
            return snapshot

        worker = spec.worker_factory()
        task = asyncio.create_task(
            worker.run(),
            name=spec.task_name or f"worker:{spec.key.id}",
        )
        self._active[spec.key.id] = _ActiveWorker(spec=spec, task=task)
        task.add_done_callback(self._build_done_callback(spec.key))
        self._registry.register(
            spec.key,
            source=spec.source,
            task_ref=task,
            task_name=task.get_name(),
        )
        return self._registry.mark_running(spec.key)

    async def stop(self, key: WorkerKey) -> WorkerSnapshot | None:
        """Stop one managed worker if it is currently active."""
        active = self._active.get(key.id)
        if active is None:
            return self._registry.get(key)

        self._registry.mark_stopping(key)
        active.task.cancel()
        with suppress(asyncio.CancelledError):
            await active.task
        self._active.pop(key.id, None)
        return self._registry.mark_stopped(key)

    async def shutdown_all(self) -> list[WorkerSnapshot]:
        """Stop all active workers and return their final snapshots."""
        snapshots: list[WorkerSnapshot] = []
        for key in self.list_active_keys():
            snapshot = await self.stop(key)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def _build_done_callback(
        self,
        key: WorkerKey,
    ) -> Callable[[asyncio.Task[None]], None]:
        """Create a typed completion callback for mypy."""
        def _callback(task: asyncio.Task[None]) -> None:
            self._handle_task_done(key, task)

        return _callback

    def _handle_task_done(self, key: WorkerKey, task: asyncio.Task[None]) -> None:
        """Update registry state when a managed task exits."""
        active = self._active.get(key.id)
        if active is not None and active.task is task:
            self._active.pop(key.id, None)

        if task.cancelled():
            snapshot = self._registry.get(key)
            if snapshot is not None and snapshot.status is not WorkerStatus.STOPPED:
                self._registry.mark_stopped(key)
            return

        error = task.exception()
        if error is not None:
            self._registry.mark_error(key, str(error))
            return

        snapshot = self._registry.get(key)
        if snapshot is not None and snapshot.status is not WorkerStatus.STOPPED:
            self._registry.mark_stopped(key)