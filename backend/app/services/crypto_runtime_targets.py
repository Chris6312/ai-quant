"""Crypto runtime target derivation."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.workers.worker_runtime_state import WorkerKey

CRYPTO_TARGET_SOURCE = "crypto scope target derivation"


@dataclass(slots=True)
class CryptoRuntimeTarget:
    key: WorkerKey


def list_crypto_runtime_targets() -> list[CryptoRuntimeTarget]:
    """Return derived crypto runtime targets.

    Phase 3/4 rule:
    crypto universe == crypto watchlist == runtime targets
    """

    symbols = list_crypto_watchlist_symbols()

    return [
        CryptoRuntimeTarget(
            key=WorkerKey(
                symbol=symbol,
                asset_class="crypto",
                timeframe="1Day",
            )
        )
        for symbol in symbols
    ]


def list_crypto_runtime_target_symbols() -> list[str]:
    """Convenience helper for symbol-only access."""
    return [target.key.symbol for target in list_crypto_runtime_targets()]