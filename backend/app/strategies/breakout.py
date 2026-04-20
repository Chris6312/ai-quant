"""Range breakout strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.indicators.library import IndicatorLib
from app.models.domain import Candle
from app.signals.base import BaseStrategy, Signal


@dataclass(slots=True, frozen=True)
class BreakoutParams:
    """Configure the breakout strategy."""

    lookback: int = 20
    volume_multiplier: float = 1.5
    strength: float = 0.7


class BreakoutStrategy(BaseStrategy):
    """Trade range breakouts with a volume filter."""

    strategy_id = "breakout"

    def __init__(self, params: BreakoutParams | None = None) -> None:
        super().__init__(max_history=250)
        self.params = params or BreakoutParams()
        self.indicators = IndicatorLib()

    @classmethod
    def from_config(cls, params: Mapping[str, object]) -> BreakoutStrategy:
        """Build a strategy from a config mapping."""

        return cls(
            BreakoutParams(
                lookback=int(params.get("lookback", 20)),
                volume_multiplier=float(params.get("volume_multiplier", 1.5)),
                strength=float(params.get("strength", 0.7)),
            )
        )

    def on_candle(self, candle: Candle, balance: float) -> Signal | None:
        """Generate a signal when price breaks the recent range."""

        history = self._append_candle(candle)
        if not history or len(history) < self.params.lookback + 1:
            return None
        recent = history[-(self.params.lookback + 1) : -1]
        highs = [item.high for item in recent]
        lows = [item.low for item in recent]
        average_volume = self.indicators.average_volume(recent, period=min(len(recent), 20))
        if average_volume == 0.0:
            return None
        if candle.close > max(highs) and candle.volume >= (
            average_volume * self.params.volume_multiplier
        ):
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="long",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=min(lows),
                tp_price=None,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        if candle.close < min(lows) and balance > 2_500.0:
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="short",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=max(highs),
                tp_price=None,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        return None
