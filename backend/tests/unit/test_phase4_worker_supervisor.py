"""Tests for the Phase 4 periodic worker supervisor."""

from __future__ import annotations

import asyncio

import pytest

from app.workers import WorkerSupervisor, WorkerSyncResult


@pytest.mark.asyncio
async def test_worker_supervisor_run_once_records_success() -> None:
    """One supervisor iteration should record result and timestamps."""

    async def _sync() -> WorkerSyncResult:
        return WorkerSyncResult(started=1, stopped=0, unchanged=2)

    supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=0.01,
        sync_operation=_sync,
    )

    result = await supervisor.run_once()
    snapshot = supervisor.snapshot()

    assert result == WorkerSyncResult(started=1, stopped=0, unchanged=2)
    assert snapshot.iteration_count == 1
    assert snapshot.last_result == result
    assert snapshot.last_success_at is not None
    assert snapshot.last_error is None


@pytest.mark.asyncio
async def test_worker_supervisor_run_once_records_error() -> None:
    """Errors should be captured without losing iteration state."""

    async def _sync() -> WorkerSyncResult:
        raise RuntimeError("sync exploded")

    supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=0.01,
        sync_operation=_sync,
    )

    with pytest.raises(RuntimeError, match="sync exploded"):
        await supervisor.run_once()

    snapshot = supervisor.snapshot()
    assert snapshot.iteration_count == 1
    assert snapshot.last_error == "sync exploded"
    assert snapshot.last_success_at is None


@pytest.mark.asyncio
async def test_worker_supervisor_start_and_stop_loop() -> None:
    """The periodic loop should execute until it is stopped."""

    calls: list[int] = []

    async def _sync() -> WorkerSyncResult:
        calls.append(len(calls) + 1)
        return WorkerSyncResult(started=0, stopped=0, unchanged=0)

    supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=0.01,
        sync_operation=_sync,
    )

    await supervisor.start()
    await asyncio.sleep(0.05)
    await supervisor.stop()

    snapshot = supervisor.snapshot()
    assert calls
    assert snapshot.running is False
    assert snapshot.iteration_count >= 1
    assert snapshot.last_finished_at is not None


@pytest.mark.asyncio
async def test_worker_supervisor_disabled_start_is_noop() -> None:
    """Disabled supervisors should not spin up a background loop."""

    async def _sync() -> WorkerSyncResult:
        return WorkerSyncResult(started=0, stopped=0, unchanged=0)

    supervisor = WorkerSupervisor(
        name="watchlist-sync",
        interval_seconds=0.01,
        sync_operation=_sync,
        enabled=False,
    )

    await supervisor.start()
    await asyncio.sleep(0)

    snapshot = supervisor.snapshot()
    assert snapshot.enabled is False
    assert snapshot.running is False
    assert snapshot.iteration_count == 0
