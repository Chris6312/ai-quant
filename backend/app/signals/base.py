"""Base signal types and strategy interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.models.domain import Candle

Direction = Literal["long", "short", "flat"]


@dataclass(slots=True, frozen=True)
class Signal:
    """Represent a trade signal from a strategy."""

    symbol: str
    asset_class: str
    direction: Direction
    strength: float
    entry_price: float
    sl_price: float | None
    tp_price: float | None
    strategy_id: str
    research_score: float


class BaseStrategy(ABC):
    """Define the strategy interface used by the signal engine."""

    strategy_id: str

    def __init__(self, max_history: int = 250) -> None:
        self._max_history = max_history
        self._history: list[Candle] = []

    def seed_history(self, candles: Sequence[Candle]) -> None:
        """Seed the internal rolling history."""

        self._history = list(candles)[-self._max_history :]

    def _append_candle(self, candle: Candle) -> list[Candle]:
        """Append a candle and return the rolling history."""

        self._history.append(candle)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        return list(self._history)

    @abstractmethod
    def on_candle(self, candle: Candle, balance: float) -> Signal | None:
        """Produce a signal from the latest candle window."""
