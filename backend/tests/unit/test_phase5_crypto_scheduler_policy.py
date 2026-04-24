"""Tests for crypto candle-close-aware scheduling policy."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.candle.crypto_scheduler import (
    get_due_strategy_timeframes,
    get_pending_strategy_timeframes,
    seconds_until_next_strategy_dispatch,
)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (datetime(2026, 4, 24, 9, 5, 20, tzinfo=UTC), ("5m",)),
        (datetime(2026, 4, 24, 9, 15, 20, tzinfo=UTC), ("5m", "15m")),
        (datetime(2026, 4, 24, 10, 0, 20, tzinfo=UTC), ("5m", "15m", "1h")),
        (datetime(2026, 4, 24, 12, 0, 20, tzinfo=UTC), ("5m", "15m", "1h", "4h")),
    ],
)
def test_get_due_strategy_timeframes_returns_only_just_closed_timeframes(
    timestamp: datetime,
    expected: tuple[str, ...],
) -> None:
    """Scheduler should queue only timeframes whose candle just closed."""

    due = get_due_strategy_timeframes(timestamp)

    assert due is not None
    assert due.timeframes == expected


def test_get_due_strategy_timeframes_waits_for_delay_after_close() -> None:
    """Scheduler should not dispatch before the 20-second close delay."""

    due = get_due_strategy_timeframes(datetime(2026, 4, 24, 9, 5, 19, tzinfo=UTC))

    assert due is None


def test_get_due_strategy_timeframes_does_not_poll_between_candle_closes() -> None:
    """Scheduler should not queue syncs on non-boundary minutes."""

    due = get_due_strategy_timeframes(datetime(2026, 4, 24, 9, 6, 20, tzinfo=UTC))

    assert due is None


def test_seconds_until_next_strategy_dispatch_targets_next_close_delay() -> None:
    """Scheduler sleep helper should target the next candle close plus delay."""

    seconds = seconds_until_next_strategy_dispatch(
        datetime(2026, 4, 24, 9, 4, 50, tzinfo=UTC)
    )

    assert seconds == 30.0


def test_pending_strategy_timeframes_catches_missed_dispatch_window() -> None:
    """Live scheduler should catch a missed 5m/15m close after the narrow window."""

    due = get_pending_strategy_timeframes(
        datetime(2026, 4, 24, 9, 16, 38, tzinfo=UTC),
        {},
    )

    assert due is not None
    assert due.timeframes == ("5m", "15m")


def test_pending_strategy_timeframes_skips_already_dispatched_close() -> None:
    """Live scheduler should not duplicate a timeframe after its close was sent."""

    dispatched = {
        "5m": datetime(2026, 4, 24, 9, 15, tzinfo=UTC).isoformat(),
        "15m": datetime(2026, 4, 24, 9, 15, tzinfo=UTC).isoformat(),
    }
    due = get_pending_strategy_timeframes(
        datetime(2026, 4, 24, 9, 16, 38, tzinfo=UTC),
        dispatched,
    )

    assert due is None
