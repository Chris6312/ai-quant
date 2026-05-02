"""Provider-neutral stock universe composition helpers.

This module builds the raw stock pool only. It does not fetch provider data,
screen candidates, score signals, write to storage, or start workers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.stock.providers import StockSymbolNormalization, normalize_stock_symbol


class StockUniverseTier(StrEnum):
    """Stock universe tiers from the S4 phase plan."""

    SP500 = "sp500"
    NASDAQ100 = "nasdaq100"
    HIGH_VOLUME = "high_volume"
    MANUAL = "manual"
    EVENT_DRIVEN = "event_driven"


class StockUniverseSource(StrEnum):
    """Provider-neutral source categories for raw stock universe inputs."""

    INDEX = "index"
    LIQUIDITY = "liquidity"
    MANUAL = "manual"
    EVENT = "event"


@dataclass(slots=True, frozen=True)
class StockUniverseCandidate:
    """One normalized stock universe candidate with raw input provenance."""

    symbol: str
    provider_symbol: str
    tiers: tuple[StockUniverseTier, ...]
    sources: tuple[StockUniverseSource, ...]
    raw_symbols: tuple[str, ...]
    is_supported: bool
    unsupported_reason: str | None = None


_TIER_ORDER: dict[StockUniverseTier, int] = {
    StockUniverseTier.SP500: 0,
    StockUniverseTier.NASDAQ100: 1,
    StockUniverseTier.HIGH_VOLUME: 2,
    StockUniverseTier.MANUAL: 3,
    StockUniverseTier.EVENT_DRIVEN: 4,
}


def normalize_symbol(symbol: str) -> StockSymbolNormalization:
    """Normalize one stock symbol using the S3 provider boundary helper."""

    return normalize_stock_symbol(symbol)


def merge_universe_sources(
    *,
    symbols: Sequence[str],
    tier: StockUniverseTier,
    source: StockUniverseSource,
) -> tuple[StockUniverseCandidate, ...]:
    """Convert one raw symbol list into normalized universe candidates."""

    candidates: list[StockUniverseCandidate] = []
    for raw_symbol in symbols:
        normalized = normalize_symbol(raw_symbol)
        candidates.append(
            StockUniverseCandidate(
                symbol=normalized.canonical_symbol,
                provider_symbol=normalized.provider_symbol,
                tiers=(tier,),
                sources=(source,),
                raw_symbols=(raw_symbol,),
                is_supported=normalized.is_supported,
                unsupported_reason=normalized.unsupported_reason,
            )
        )
    return tuple(candidates)


def dedupe_candidates(
    candidates: Iterable[StockUniverseCandidate],
) -> tuple[StockUniverseCandidate, ...]:
    """Deduplicate candidates while preserving tier and source provenance."""

    by_symbol: dict[str, StockUniverseCandidate] = {}
    for candidate in candidates:
        normalized = normalize_symbol(candidate.symbol)
        normalized_candidate = StockUniverseCandidate(
            symbol=normalized.canonical_symbol,
            provider_symbol=normalized.provider_symbol,
            tiers=candidate.tiers,
            sources=candidate.sources,
            raw_symbols=candidate.raw_symbols,
            is_supported=candidate.is_supported and normalized.is_supported,
            unsupported_reason=candidate.unsupported_reason or normalized.unsupported_reason,
        )
        existing = by_symbol.get(normalized_candidate.symbol)
        if existing is None:
            by_symbol[normalized_candidate.symbol] = normalized_candidate
            continue

        by_symbol[normalized_candidate.symbol] = StockUniverseCandidate(
            symbol=existing.symbol,
            provider_symbol=existing.provider_symbol,
            tiers=_merge_tiers(existing.tiers, normalized_candidate.tiers),
            sources=_merge_sources(existing.sources, normalized_candidate.sources),
            raw_symbols=_merge_strings(existing.raw_symbols, normalized_candidate.raw_symbols),
            is_supported=existing.is_supported and normalized_candidate.is_supported,
            unsupported_reason=existing.unsupported_reason
            or normalized_candidate.unsupported_reason,
        )

    return tuple(sorted(by_symbol.values(), key=_candidate_sort_key))


def build_stock_universe(
    *,
    sp500: Sequence[str] = (),
    nasdaq100: Sequence[str] = (),
    high_volume: Sequence[str] = (),
    manual: Sequence[str] = (),
    event_driven: Sequence[str] = (),
) -> tuple[StockUniverseCandidate, ...]:
    """Build the raw stock universe from S4 tier inputs."""

    candidates: list[StockUniverseCandidate] = []
    candidates.extend(
        merge_universe_sources(
            symbols=sp500,
            tier=StockUniverseTier.SP500,
            source=StockUniverseSource.INDEX,
        )
    )
    candidates.extend(
        merge_universe_sources(
            symbols=nasdaq100,
            tier=StockUniverseTier.NASDAQ100,
            source=StockUniverseSource.INDEX,
        )
    )
    candidates.extend(
        merge_universe_sources(
            symbols=high_volume,
            tier=StockUniverseTier.HIGH_VOLUME,
            source=StockUniverseSource.LIQUIDITY,
        )
    )
    candidates.extend(
        merge_universe_sources(
            symbols=manual,
            tier=StockUniverseTier.MANUAL,
            source=StockUniverseSource.MANUAL,
        )
    )
    candidates.extend(
        merge_universe_sources(
            symbols=event_driven,
            tier=StockUniverseTier.EVENT_DRIVEN,
            source=StockUniverseSource.EVENT,
        )
    )
    return dedupe_candidates(candidates)


def _merge_tiers(
    left: tuple[StockUniverseTier, ...],
    right: tuple[StockUniverseTier, ...],
) -> tuple[StockUniverseTier, ...]:
    tiers = set(left)
    tiers.update(right)
    return tuple(sorted(tiers, key=lambda tier: _TIER_ORDER[tier]))


def _merge_sources(
    left: tuple[StockUniverseSource, ...],
    right: tuple[StockUniverseSource, ...],
) -> tuple[StockUniverseSource, ...]:
    sources = set(left)
    sources.update(right)
    return tuple(sorted(sources, key=lambda source: source.value))


def _merge_strings(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for value in (*left, *right):
        if value in seen:
            continue
        values.append(value)
        seen.add(value)
    return tuple(values)


def _candidate_sort_key(
    candidate: StockUniverseCandidate,
) -> tuple[int, str]:
    first_tier = candidate.tiers[0] if candidate.tiers else StockUniverseTier.EVENT_DRIVEN
    return (_TIER_ORDER[first_tier], candidate.symbol)


__all__ = [
    "StockUniverseCandidate",
    "StockUniverseSource",
    "StockUniverseTier",
    "build_stock_universe",
    "dedupe_candidates",
    "merge_universe_sources",
    "normalize_symbol",
]
