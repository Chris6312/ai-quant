"""Momentum crossover strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.config.constants import STOCK_SHORT_BALANCE_THRESHOLD
from app.indicators.library import IndicatorLib
from app.models.domain import Candle
from app.signals.base import BaseStrategy, Signal


@dataclass(slots=True, frozen=True)
class MomentumParams:
    """Configure the momentum strategy."""

    fast_period: int = 8
    slow_period: int = 21
    adx_threshold: float = 25.0
    strength: float = 0.75


class MomentumStrategy(BaseStrategy):
    """Trade EMA crossovers with an ADX trend filter."""

    strategy_id = "momentum"

    def __init__(self, params: MomentumParams | None = None) -> None:
        super().__init__(max_history=250)
        self.params = params or MomentumParams()
        self.indicators = IndicatorLib()

    @classmethod
    def from_config(cls, params: Mapping[str, object]) -> MomentumStrategy:
        """Build a strategy from a config mapping."""

        return cls(
            MomentumParams(
                fast_period=int(cast(int | float | str, params.get("fast_period", 8))),
                slow_period=int(cast(int | float | str, params.get("slow_period", 21))),
                adx_threshold=float(cast(int | float | str, params.get("adx_threshold", 25.0))),
                strength=float(cast(int | float | str, params.get("strength", 0.75))),
            )
        )

    def on_candle(self, candle: Candle, balance: float) -> Signal | None:
        """Generate a signal from the latest candle window."""

        history = self._append_candle(candle)
        if not history or len(history) < self.params.slow_period + 2:
            return None
        previous = history[:-1]
        closes = self.indicators.closes(previous)
        fast_ema = self.indicators.ema(closes, self.params.fast_period)
        slow_ema = self.indicators.ema(closes, self.params.slow_period)
        if not fast_ema or not slow_ema:
            return None
        adx_value = self.indicators.adx(history, period=14)
        if adx_value < self.params.adx_threshold:
            return None
        if candle.close > previous[-1].close and fast_ema[-1] > slow_ema[-1]:
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="long",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=None,
                tp_price=None,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        if candle.asset_class != "stock":
            return None
        if (
            candle.close < previous[-1].close
            and fast_ema[-1] < slow_ema[-1]
            and balance > STOCK_SHORT_BALANCE_THRESHOLD
        ):
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="short",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=None,
                tp_price=None,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        return None
