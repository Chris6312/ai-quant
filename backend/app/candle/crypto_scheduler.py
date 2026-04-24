"""Crypto candle-close scheduling helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

CRYPTO_CANDLE_CLOSE_DELAY_SECONDS = 20
CRYPTO_DISPATCH_GRACE_SECONDS = 5
CRYPTO_SCHEDULED_TRADING_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "4h")
_TIMEFRAME_SECONDS: dict[str, int] = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
}


class CeleryTaskDispatcher(Protocol):
    """Minimal task-dispatch protocol used by crypto candle schedulers."""

    def send_task(self, name: str, kwargs: dict[str, object]) -> object:
        """Submit a task by name."""


@dataclass(frozen=True, slots=True)
class DueStrategyTimeframes:
    """Timeframes due for one closed-candle dispatch window."""

    close_at: datetime
    dispatch_at: datetime
    timeframes: tuple[str, ...]


def _latest_closed_at(now: datetime, timeframe: str) -> datetime:
    """Return the latest closed candle boundary for one timeframe."""

    now_utc = now.astimezone(UTC)
    interval_seconds = _TIMEFRAME_SECONDS[timeframe]
    close_epoch = int(now_utc.timestamp()) // interval_seconds * interval_seconds
    return datetime.fromtimestamp(close_epoch, tz=UTC)


def get_due_strategy_timeframes(now: datetime) -> DueStrategyTimeframes | None:
    """Return strategy timeframes due exactly after a candle close delay."""

    now_utc = now.astimezone(UTC)
    adjusted = now_utc - timedelta(seconds=CRYPTO_CANDLE_CLOSE_DELAY_SECONDS)

    if adjusted.second >= CRYPTO_DISPATCH_GRACE_SECONDS:
        return None

    seconds_since_midnight = adjusted.hour * 60 * 60 + adjusted.minute * 60
    timeframes = tuple(
        timeframe
        for timeframe in CRYPTO_SCHEDULED_TRADING_TIMEFRAMES
        if seconds_since_midnight % _TIMEFRAME_SECONDS[timeframe] == 0
    )
    if not timeframes:
        return None

    close_at = adjusted.replace(second=0, microsecond=0)
    return DueStrategyTimeframes(
        close_at=close_at,
        dispatch_at=close_at + timedelta(seconds=CRYPTO_CANDLE_CLOSE_DELAY_SECONDS),
        timeframes=timeframes,
    )


def get_pending_strategy_timeframes(
    now: datetime,
    dispatched_close_ids: dict[str, str],
) -> DueStrategyTimeframes | None:
    """Return the latest pending closed-candle window.

    This catches missed dispatch windows without backfilling older timeframe
    windows in the live scheduler. At 09:16:38, the latest closed boundary is
    09:15, so only 5m and 15m are eligible. It must not fall back to older
    1h or 4h closes from 09:00 or 08:00.
    """

    now_utc = now.astimezone(UTC)
    latest_close_by_timeframe = {
        timeframe: _latest_closed_at(now_utc, timeframe)
        for timeframe in CRYPTO_SCHEDULED_TRADING_TIMEFRAMES
    }
    latest_close_at = max(latest_close_by_timeframe.values())
    dispatch_at = latest_close_at + timedelta(seconds=CRYPTO_CANDLE_CLOSE_DELAY_SECONDS)

    if now_utc < dispatch_at:
        return None

    pending_timeframes = tuple(
        timeframe
        for timeframe, close_at in latest_close_by_timeframe.items()
        if close_at == latest_close_at
        and dispatched_close_ids.get(timeframe) != close_at.isoformat()
    )
    if not pending_timeframes:
        return None

    return DueStrategyTimeframes(
        close_at=latest_close_at,
        dispatch_at=dispatch_at,
        timeframes=pending_timeframes,
    )


def due_crypto_timeframes(now: datetime) -> list[str]:
    """Return crypto trading timeframes whose candle just closed plus delay."""

    due = get_due_strategy_timeframes(now)
    if due is None:
        return []
    return list(due.timeframes)


def crypto_dispatch_close_id(now: datetime) -> str:
    """Return the candle-close identifier for the current dispatch window."""

    adjusted = now.astimezone(UTC) - timedelta(
        seconds=CRYPTO_CANDLE_CLOSE_DELAY_SECONDS
    )
    return adjusted.replace(second=0, microsecond=0).isoformat()

def latest_crypto_close_id(now: datetime, timeframe: str) -> str | None:
    """Return the latest closed candle identifier for one timeframe."""

    if timeframe not in _TIMEFRAME_SECONDS:
        return None
    return _latest_closed_at(now, timeframe).isoformat()

def next_crypto_candle_dispatch_at(now: datetime) -> datetime:
    """Return the next scheduled crypto closed-candle dispatch timestamp."""

    now_utc = now.astimezone(UTC)
    current_epoch = int(now_utc.timestamp())
    candidates: list[datetime] = []

    for seconds in _TIMEFRAME_SECONDS.values():
        next_close_epoch = ((current_epoch // seconds) + 1) * seconds
        next_dispatch = datetime.fromtimestamp(next_close_epoch, tz=UTC) + timedelta(
            seconds=CRYPTO_CANDLE_CLOSE_DELAY_SECONDS
        )
        if next_dispatch <= now_utc:
            next_dispatch += timedelta(seconds=seconds)
        candidates.append(next_dispatch)

    return min(candidates)


def seconds_until_next_strategy_dispatch(now: datetime) -> float:
    """Return seconds until the next candle-close dispatch window."""

    now_utc = now.astimezone(UTC)
    return max(0.0, (next_crypto_candle_dispatch_at(now_utc) - now_utc).total_seconds())


class CryptoCandleScheduler:
    """Dispatch crypto candle tasks for the current crypto target set."""

    def __init__(self, dispatcher: CeleryTaskDispatcher) -> None:
        self._dispatcher = dispatcher
        self._running = False
        self._dispatched_close_ids: dict[str, str] = {}

    async def run(self) -> None:
        """Run dispatch cycles until stopped."""

        self._running = True
        while self._running:
            await self.dispatch_once()
            await asyncio.sleep(seconds_until_next_strategy_dispatch(datetime.now(UTC)))

    async def dispatch_once(self, now: datetime | None = None) -> None:
        """Dispatch one closed-candle sync cycle when a timeframe is due."""

        now_utc = (now or datetime.now(UTC)).astimezone(UTC)
        due = get_pending_strategy_timeframes(now_utc, self._dispatched_close_ids)
        if due is None:
            return

        for timeframe in due.timeframes:
            self._dispatched_close_ids[timeframe] = due.close_at.isoformat()

        from app.services.crypto_runtime_targets import list_crypto_runtime_targets
        from app.tasks.crypto_candles import build_crypto_sync_task_payload

        symbols = [target.key.symbol for target in list_crypto_runtime_targets()]
        payload = build_crypto_sync_task_payload(
            symbols=symbols,
            timeframes=list(due.timeframes),
        )
        payload.kwargs["requested_at"] = now_utc.isoformat()
        payload.kwargs["candle_close_at"] = due.close_at.isoformat()
        self._dispatcher.send_task(payload.name, kwargs=payload.kwargs)

    def stop(self) -> None:
        """Stop the scheduler after the current sleep/cycle completes."""

        self._running = False