"""Background supervision loop for Phase 4 worker orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from app.workers.worker_lifecycle import WorkerSyncResult


@dataclass(frozen=True, slots=True)
class WorkerSupervisorSnapshot:
    """Observable runtime state for the worker supervisor."""

    name: str
    enabled: bool
    running: bool
    interval_seconds: int
    iteration_count: int
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    last_result: WorkerSyncResult | None


class WorkerSupervisor:
    """Periodically run a worker synchronization operation."""

    def __init__(
        self,
        *,
        name: str,
        sync_operation: Callable[[], Awaitable[WorkerSyncResult]],
        interval_seconds: int,
        enabled: bool = True,
    ) -> None:

        self._name = name
        self._sync_operation = sync_operation
        self._interval_seconds = int(interval_seconds)
        self._enabled = enabled

        self._iteration_count = 0
        self._last_started_at: datetime | None = None
        self._last_finished_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_error: str | None = None
        self._last_result: WorkerSyncResult | None = None

        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def snapshot(self) -> WorkerSupervisorSnapshot:

        return WorkerSupervisorSnapshot(
            name=self._name,
            enabled=self._enabled,
            running=self.running,
            interval_seconds=self._interval_seconds,
            iteration_count=self._iteration_count,
            last_started_at=self._last_started_at,
            last_finished_at=self._last_finished_at,
            last_success_at=self._last_success_at,
            last_error=self._last_error,
            last_result=self._last_result,
        )

    async def start(self) -> None:

        if not self._enabled or self.running:
            return

        self._stop_event = asyncio.Event()

        self._task = asyncio.create_task(
            self._run_loop(),
            name=f"worker-supervisor:{self._name}",
        )

    async def stop(self) -> None:

        task = self._task

        if task is None:
            return

        self._stop_event.set()

        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        self._task = None

    async def run_once(self) -> WorkerSyncResult:

        now = datetime.now(tz=UTC)

        self._iteration_count += 1
        self._last_started_at = now
        self._last_error = None

        try:

            result = await self._sync_operation()

        except Exception as exc:

            self._last_finished_at = datetime.now(tz=UTC)
            self._last_error = str(exc)

            raise

        finished_at = datetime.now(tz=UTC)

        self._last_finished_at = finished_at
        self._last_success_at = finished_at
        self._last_result = result

        return result

    async def _run_loop(self) -> None:

        while not self._stop_event.is_set():

            await self.run_once()

            try:

                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )

            except TimeoutError:

                continue