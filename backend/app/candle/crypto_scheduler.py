"""Single crypto candle scheduler for Celery-backed candle work."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.services.crypto_runtime_targets import list_crypto_runtime_targets
from app.tasks.crypto_candles import build_crypto_celery_task_payloads
from app.workers.crypto_worker_sync import CeleryTaskDispatcher


class CryptoCandleScheduler:
    """Dispatch crypto candle tasks for the current crypto target set."""

    def __init__(
        self,
        dispatcher: CeleryTaskDispatcher,
        interval_seconds: int = 60,
    ) -> None:
        self._dispatcher = dispatcher
        self._interval_seconds = interval_seconds
        self._running = False

    async def run(self) -> None:
        """Run dispatch cycles until stopped."""

        self._running = True
        while self._running:
            await self.dispatch_once()
            await asyncio.sleep(self._interval_seconds)

    async def dispatch_once(self) -> None:
        """Dispatch one candle-sync cycle for all crypto runtime targets."""

        now = datetime.now(UTC)
        symbols = [target.key.symbol for target in list_crypto_runtime_targets()]
        for payload in build_crypto_celery_task_payloads(symbols):
            payload.kwargs["requested_at"] = now.isoformat()
            self._dispatcher.send_task(payload.name, kwargs=payload.kwargs)

    def stop(self) -> None:
        """Stop the scheduler after the current sleep/cycle completes."""

        self._running = False
