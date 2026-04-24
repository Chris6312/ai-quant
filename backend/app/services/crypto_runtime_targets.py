"""Helpers for deriving crypto runtime worker targets from backend truth."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.workers.worker_runtime_state import WorkerKey

CRYPTO_RUNTIME_TIMEFRAME = "1Day"
CRYPTO_TARGET_SOURCE = "crypto scope target derivation"


@dataclass(frozen=True, slots=True)
class CryptoRuntimeTarget:
    """One derived crypto runtime target."""

    key: WorkerKey
    source: str = CRYPTO_TARGET_SOURCE


def list_crypto_runtime_targets() -> list[CryptoRuntimeTarget]:
    """Return the desired crypto runtime targets for the current phase.

    For the crypto-first rollout, the crypto watchlist mirrors the canonical
    universe. Runtime target derivation is explicit and deterministic so the UI
    can distinguish universe size from intended worker targets and attached
    worker state.
    """

    return [
        CryptoRuntimeTarget(
            key=WorkerKey(
                symbol=symbol,
                asset_class="crypto",
                timeframe=CRYPTO_RUNTIME_TIMEFRAME,
            )
        )
        for symbol in list_crypto_watchlist_symbols()
    ]
