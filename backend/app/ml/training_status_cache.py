from __future__ import annotations

import json
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_CACHE_PATH = _RUNTIME_DIR / "ml_training_status.json"


class TrainingStatusCacheRecord(TypedDict):
    source: str
    total_candles: int
    crypto_candles: int
    stock_candles: int
    crypto_symbols: int
    stock_symbols: int
    symbols_with_data: int
    crypto_detail: list[dict[str, object]]
    stock_detail: list[dict[str, object]]
    generated_at: str
    cache_state: str


async def get_or_build_training_status(
    builder: Callable[[], Awaitable[dict[str, object]]],
) -> TrainingStatusCacheRecord:
    cached = load_training_status()
    if cached is not None:
        return cached
    return await rebuild_training_status(builder)


async def rebuild_training_status(
    builder: Callable[[], Awaitable[dict[str, object]]],
) -> TrainingStatusCacheRecord:
    built = await builder()
    now = datetime.now(UTC).isoformat()
    record = cast(
        TrainingStatusCacheRecord,
        {
            **built,
            "generated_at": now,
            "cache_state": "fresh",
        },
    )
    _save_training_status(record)
    return record


def load_training_status() -> TrainingStatusCacheRecord | None:
    with _LOCK:
        if not _CACHE_PATH.exists():
            return None
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    return cast(TrainingStatusCacheRecord, data)


def invalidate_training_status() -> None:
    with _LOCK:
        if _CACHE_PATH.exists():
            _CACHE_PATH.unlink()


def _save_training_status(record: TrainingStatusCacheRecord) -> None:
    with _LOCK:
        _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
