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
    "LTC/USD",
    "BCH/USD",
    "LINK/USD",
    "UNI/USD",
    "AVAX/USD",
    "DOGE/USD",
    "DOT/USD",
    "AAVE/USD",
    "CRV/USD",
    "SUSHI/USD",
    "SHIB/USD",
    "XTZ/USD",
)
"""Canonical crypto universe for the runtime Kraken lane."""


CRYPTO_ML_SYMBOL_ALIASES: Final[dict[str, str]] = {
    "DOGE/USD": "XDG/USD",
}
"""Storage aliases for the ML candle lane. Runtime can still display DOGE/USD."""


def canonicalize_crypto_ml_symbol(symbol: str) -> str:
    """Return the canonical storage symbol for crypto ML candles and scoring."""

    normalized = symbol.upper()
    return CRYPTO_ML_SYMBOL_ALIASES.get(normalized, normalized)


def list_crypto_ml_symbols() -> list[str]:
    """Return canonical crypto symbols expected in the ML candle lane."""

    symbols = {canonicalize_crypto_ml_symbol(symbol) for symbol in KRAKEN_UNIVERSE}
    return sorted(symbols)

CRYPTO_SCOPE_MODEL: Final[dict[str, str]] = {
    "crypto_universe": (
        "Canonical crypto symbol set for the current crypto-first rollout. "
        "This is the fixed Kraken universe until later runtime phases derive "
        "a narrower active set."
    ),
    "crypto_watchlist": (
        "Operator-facing crypto list. It is intentionally identical to the "
        "crypto universe right now so the app does not invent a second source "
        "of truth before runtime derivation exists."
    ),
    "active_runtime_set": (
        "Symbols that currently have runtime workers attached. This starts "
        "empty until a later phase attaches crypto worker targets."
    ),
    "prediction_set": (
        "Symbols with persisted inference rows. This is a downstream ML/runtime "
        "result, not the scope source of truth."
    ),
}

CRYPTO_SCOPE_MAPPING: Final[dict[str, str]] = {
    "crypto_universe": "KRAKEN_UNIVERSE",
    "crypto_watchlist": "Same as crypto universe for the current crypto-first phase",
    "active_runtime_set": "Derived from attached runtime workers when available",
    "prediction_set": "Derived from persisted inference output",
}

# Backward-compatible alias for prior handoffs and references.
CRYPTO_SCOPE_PHASE_1_MAPPING: Final[dict[str, str]] = CRYPTO_SCOPE_MAPPING


def list_crypto_universe_symbols() -> list[str]:
    """Return the canonical crypto universe as a mutable list."""

    return list(KRAKEN_UNIVERSE)


def list_crypto_watchlist_symbols() -> list[str]:
    """Return the current operator-facing crypto watchlist symbols."""

    return list_crypto_universe_symbols()


def is_phase_1_crypto_symbol(symbol: str) -> bool:
    """Return whether a symbol belongs to the canonical crypto scope."""

    return symbol.upper() in KRAKEN_UNIVERSE
