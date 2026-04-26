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

_RESEARCH_CRYPTO_PROMOTED_SYMBOLS: list[str] = []
"""Process-local soft watchlist for Research visibility only.

This intentionally does not feed worker, ML, or execution scope. It exists so
Phase 2A can let the operator focus the Research page without changing runtime
behavior before the later execution-scope phases.
"""


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
        "Runtime-facing crypto list. It intentionally remains identical to the "
        "crypto universe right now so workers and ML do not inherit the Phase "
        "2A research-only promoted list."
    ),
    "research_crypto_promoted": (
        "Operator-facing soft watchlist for the Research page. If empty, "
        "Research falls back to the full crypto universe. It is visibility-only "
        "and does not drive workers, ML, paper trading, or live execution."
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
    "crypto_watchlist": "Same as crypto universe for runtime during this phase",
    "research_crypto_promoted": "Research-only soft watchlist with universe fallback",
    "active_runtime_set": "Derived from attached runtime workers when available",
    "prediction_set": "Derived from persisted inference output",
}

# Backward-compatible alias for prior handoffs and references.
CRYPTO_SCOPE_PHASE_1_MAPPING: Final[dict[str, str]] = CRYPTO_SCOPE_MAPPING


def list_crypto_universe_symbols() -> list[str]:
    """Return the canonical crypto universe as a mutable list."""

    return list(KRAKEN_UNIVERSE)


def list_crypto_watchlist_symbols() -> list[str]:
    """Return the runtime-facing crypto watchlist symbols."""

    return list_crypto_universe_symbols()


def _normalize_research_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def list_research_crypto_promoted_symbols() -> list[str]:
    """Return the Research-only promoted crypto symbols."""

    return list(_RESEARCH_CRYPTO_PROMOTED_SYMBOLS)


def list_research_crypto_scope_symbols() -> list[str]:
    """Return Research crypto scope, falling back to full universe when empty."""

    promoted = list_research_crypto_promoted_symbols()
    if promoted:
        return promoted
    return list_crypto_universe_symbols()


def get_research_crypto_scope_source() -> str:
    """Return a plain-English source label for the Research crypto scope."""

    if _RESEARCH_CRYPTO_PROMOTED_SYMBOLS:
        return "research promoted crypto"
    return "crypto universe"


def set_research_crypto_promoted_symbols(symbols: list[str]) -> list[str]:
    """Replace the Research-only promoted crypto list after universe validation."""

    normalized_unique = {_normalize_research_symbol(symbol) for symbol in symbols}
    universe = list_crypto_universe_symbols()
    universe_set = set(universe)
    invalid_symbols = sorted(normalized_unique - universe_set)
    if invalid_symbols:
        invalid_text = ", ".join(invalid_symbols)
        raise ValueError(f"Unknown crypto symbol(s): {invalid_text}")

    _RESEARCH_CRYPTO_PROMOTED_SYMBOLS.clear()
    _RESEARCH_CRYPTO_PROMOTED_SYMBOLS.extend(
        symbol for symbol in universe if symbol in normalized_unique
    )
    return list_research_crypto_promoted_symbols()


def clear_research_crypto_promoted_symbols() -> None:
    """Clear the Research-only promoted crypto list."""

    _RESEARCH_CRYPTO_PROMOTED_SYMBOLS.clear()


def is_phase_1_crypto_symbol(symbol: str) -> bool:
    """Return whether a symbol belongs to the canonical crypto scope."""

    return symbol.upper() in KRAKEN_UNIVERSE
