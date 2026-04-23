"""Canonical crypto scope semantics for the crypto-first rollout.

This module defines the operator-facing and backend-facing meaning of the
crypto lane so later runtime, worker, and prediction slices can derive from a
single source of truth instead of stock-watchlist assumptions.
"""

from __future__ import annotations

from typing import Final

KRAKEN_UNIVERSE: Final[tuple[str, ...]] = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "ADA/USD",
    "AVAX/USD",
    "DOT/USD",
    "LINK/USD",
    "MATIC/USD",
    "LTC/USD",
    "UNI/USD",
    "ATOM/USD",
    "NEAR/USD",
    "ALGO/USD",
    "FIL/USD",
)
"""Canonical crypto universe for the runtime Kraken lane in Phase 1."""

CRYPTO_SCOPE_MODEL: Final[dict[str, str]] = {
    "crypto_universe": (
        "Canonical crypto symbol set for the current crypto-first rollout. "
        "In Phase 1 this is the fixed Kraken universe."
    ),
    "crypto_watchlist": (
        "Operator-facing crypto list. In Phase 1 it is intentionally identical "
        "to the crypto universe so the app does not invent a second source of truth."
    ),
    "active_runtime_set": (
        "Symbols that should eventually have runtime workers attached. This is "
        "derived from crypto scope in later phases, not hand-curated here."
    ),
    "prediction_set": (
        "Symbols with persisted inference rows. This is a downstream ML/runtime "
        "result, not the scope source of truth."
    ),
}

CRYPTO_SCOPE_PHASE_1_MAPPING: Final[dict[str, str]] = {
    "crypto_universe": "KRAKEN_UNIVERSE",
    "crypto_watchlist": "Same as crypto universe for Phase 1",
    "active_runtime_set": "Derived in later runtime phases",
    "prediction_set": "Derived from persisted inference output",
}


def is_phase_1_crypto_symbol(symbol: str) -> bool:
    """Return whether a symbol belongs to the Phase 1 canonical crypto scope."""

    return symbol.upper() in KRAKEN_UNIVERSE
