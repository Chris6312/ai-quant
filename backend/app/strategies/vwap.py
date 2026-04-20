"""VWAP deviation strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.indicators.library import IndicatorLib
from app.models.domain import Candle
from app.signals.base import BaseStrategy, Signal


@dataclass(slots=True, frozen=True)
class VWAPParams:
    """Configure the VWAP deviation strategy."""

    deviation_stdevs: float = 1.5
    strength: float = 0.6


class VWAPStrategy(BaseStrategy):
    """Trade significant deviations below VWAP with volume confirmation."""

    strategy_id = "vwap"

    def __init__(self, params: VWAPParams | None = None) -> None:
        super().__init__(max_history=250)
        self.params = params or VWAPParams()
        self.indicators = IndicatorLib()

    @classmethod
    def from_config(cls, params: Mapping[str, object]) -> VWAPStrategy:
        """Build a strategy from a config mapping."""

        return cls(
            VWAPParams(
                deviation_stdevs=float(params.get("deviation_stdevs", 1.5)),
                strength=float(params.get("strength", 0.6)),
            )
        )

    def on_candle(self, candle: Candle, balance: float) -> Signal | None:
        """Generate a long signal when price is stretched under VWAP."""

        history = self._append_candle(candle)
        if not history or len(history) < 20:
            return None
        previous = history[:-1]
        closes = self.indicators.closes(previous)
        vwap = self.indicators.vwap(previous)
        bands = self.indicators.bollinger_bands(closes, 20, self.params.deviation_stdevs)
        if not bands:
            return None
        middle, _, lower = bands[-1]
        if candle.close < vwap and candle.close <= lower:
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="long",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=lower,
                tp_price=middle,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        return None
