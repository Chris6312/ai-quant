from __future__ import annotations

import json
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

_LOCK = threading.Lock()
_RUNTIME_DIR = Path("backend/.runtime")
_CACHE_PATH = _RUNTIME_DIR / "ml_training_status.json"
_CACHE_SCHEMA_VERSION = 2
_DEFAULT_MAX_AGE = timedelta(minutes=5)


class TrainingStatusCacheRecord(TypedDict, total=False):
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
    schema_version: int
    invalidated_at: str | None
    invalidation_reason: str | None


async def get_or_build_training_status(
    builder: Callable[[], Awaitable[dict[str, object]]],
    *,
    allow_stale: bool = False,
    max_age: timedelta = _DEFAULT_MAX_AGE,
) -> TrainingStatusCacheRecord:
    cached = load_training_status()
    if cached is not None and _is_cache_usable(
        cached,
        allow_stale=allow_stale,
        max_age=max_age,
    ):
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
            "schema_version": _CACHE_SCHEMA_VERSION,
            "invalidated_at": None,
            "invalidation_reason": None,
        },
    )
    _save_training_status(record)
    return record


def load_training_status() -> TrainingStatusCacheRecord | None:
    with _LOCK:
        if not _CACHE_PATH.exists():
            return None
        try:
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _CACHE_PATH.unlink(missing_ok=True)
            return None

    record = cast(TrainingStatusCacheRecord, data)
    if not _looks_like_training_status(record):
        with _LOCK:
            _CACHE_PATH.unlink(missing_ok=True)
        return None
    return record


def invalidate_training_status(reason: str = "manual") -> None:
    with _LOCK:
        if _CACHE_PATH.exists():
            _CACHE_PATH.unlink()


def mark_training_status_stale(reason: str) -> TrainingStatusCacheRecord | None:
    with _LOCK:
        if not _CACHE_PATH.exists():
            return None
        try:
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _CACHE_PATH.unlink(missing_ok=True)
            return None

        record = cast(TrainingStatusCacheRecord, data)
        if not _looks_like_training_status(record):
            _CACHE_PATH.unlink(missing_ok=True)
            return None

        record["cache_state"] = "stale"
        record["schema_version"] = _CACHE_SCHEMA_VERSION
        record["invalidated_at"] = datetime.now(UTC).isoformat()
        record["invalidation_reason"] = reason
        _save_training_status_unlocked(record)
        return record


def _save_training_status(record: TrainingStatusCacheRecord) -> None:
    with _LOCK:
        _save_training_status_unlocked(record)


def _save_training_status_unlocked(record: TrainingStatusCacheRecord) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _is_cache_usable(
    record: TrainingStatusCacheRecord,
    *,
    allow_stale: bool,
    max_age: timedelta,
) -> bool:
    state = record.get("cache_state")
    if state == "stale":
        return allow_stale
    if state != "fresh":
        return False
    return not _is_expired(record, max_age=max_age)


def _is_expired(record: TrainingStatusCacheRecord, *, max_age: timedelta) -> bool:
    generated_at = record.get("generated_at")
    if not generated_at:
        return True
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        return True
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    age = datetime.now(UTC) - generated.astimezone(UTC)
    return age > max_age


def _looks_like_training_status(record: TrainingStatusCacheRecord) -> bool:
    required_keys = {
        "source",
        "total_candles",
        "crypto_candles",
        "stock_candles",
        "crypto_symbols",
        "stock_symbols",
        "symbols_with_data",
        "crypto_detail",
        "stock_detail",
        "generated_at",
        "cache_state",
    }
    if not required_keys.issubset(record):
        return False
    return record.get("schema_version", _CACHE_SCHEMA_VERSION) == _CACHE_SCHEMA_VERSION