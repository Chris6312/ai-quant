"""Utilities for loading and normalizing the stock training universe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_UNSUPPORTED_PROVIDER_CHARS: Final[tuple[str, ...]] = (".", "/")


@dataclass(slots=True, frozen=True)
class StockUniverseSymbol:
    """Normalized stock universe symbol metadata."""

    symbol: str
    security: str
    sector: str
    sub_industry: str
    provider_symbol: str
    is_supported: bool
    unsupported_reason: str | None


@dataclass(slots=True, frozen=True)
class StockUniverseSnapshot:
    """Structured view of the S&P 500 training universe file."""

    index_name: str
    as_of: str
    constituent_stock_count: int
    file_path: Path
    symbols: tuple[StockUniverseSymbol, ...]

    @property
    def supported_symbols(self) -> tuple[StockUniverseSymbol, ...]:
        """Return the subset that can be fetched with the current provider rules."""

        return tuple(symbol for symbol in self.symbols if symbol.is_supported)

    @property
    def unsupported_symbols(self) -> tuple[StockUniverseSymbol, ...]:
        """Return the subset skipped for provider compatibility reasons."""

        return tuple(symbol for symbol in self.symbols if not symbol.is_supported)


class StockUniverseLoader:
    """Load the canonical stock universe from the checked-in S&P 500 JSON file."""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path or self._default_file_path()

    def load(self) -> StockUniverseSnapshot:
        """Parse the S&P 500 universe JSON file and normalize the symbol list."""

        payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            msg = "stock universe file must contain a JSON object"
            raise ValueError(msg)

        raw_rows = payload.get("constituents", [])
        if not isinstance(raw_rows, list):
            msg = "stock universe constituents must be a list"
            raise ValueError(msg)

        symbols: list[StockUniverseSymbol] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            symbol = str(raw_row.get("Symbol", "")).strip().upper()
            if not symbol:
                continue
            provider_symbol, unsupported_reason = self._provider_symbol(symbol)
            symbols.append(
                StockUniverseSymbol(
                    symbol=symbol,
                    security=str(raw_row.get("Security", "")).strip(),
                    sector=str(raw_row.get("GICS Sector", "")).strip(),
                    sub_industry=str(raw_row.get("GICS Sub-Industry", "")).strip(),
                    provider_symbol=provider_symbol,
                    is_supported=unsupported_reason is None,
                    unsupported_reason=unsupported_reason,
                )
            )

        constituent_stock_count = payload.get("constituent_stock_count")
        count = (
            constituent_stock_count
            if isinstance(constituent_stock_count, int)
            else len(symbols)
        )

        return StockUniverseSnapshot(
            index_name=str(payload.get("index", "S&P 500")),
            as_of=str(payload.get("as_of", "")),
            constituent_stock_count=count,
            file_path=self.file_path,
            symbols=tuple(symbols),
        )

    @staticmethod
    def _default_file_path() -> Path:
        return Path(__file__).resolve().parents[3] / "SP500" / "sp500_constituents_2026-04-22.json"

    @staticmethod
    def _provider_symbol(symbol: str) -> tuple[str, str | None]:
        for unsupported_char in _UNSUPPORTED_PROVIDER_CHARS:
            if unsupported_char in symbol:
                return symbol, f"contains unsupported provider character '{unsupported_char}'"
        return symbol, None
