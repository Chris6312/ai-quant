"""Mean reversion strategy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.indicators.library import IndicatorLib
from app.models.domain import Candle
from app.signals.base import BaseStrategy, Signal


@dataclass(slots=True, frozen=True)
class MeanReversionParams:
    """Configure the mean reversion strategy."""

    rsi_period: int = 14
    rsi_oversold: float = 30.0
    bollinger_period: int = 20
    strength: float = 0.65


class MeanReversionStrategy(BaseStrategy):
    """Trade oversold moves back toward the mean."""

    strategy_id = "mean_reversion"

    def __init__(self, params: MeanReversionParams | None = None) -> None:
        super().__init__(max_history=250)
        self.params = params or MeanReversionParams()
        self.indicators = IndicatorLib()

    @classmethod
    def from_config(cls, params: Mapping[str, object]) -> MeanReversionStrategy:
        """Build a strategy from a config mapping."""

        rsi_period = cast(int | str, params.get("rsi_period", 14))
        rsi_oversold = cast(float | int | str, params.get("rsi_oversold", 30.0))
        bollinger_period = cast(int | str, params.get("bollinger_period", 20))
        strength = cast(float | int | str, params.get("strength", 0.65))
        return cls(
            MeanReversionParams(
                rsi_period=int(rsi_period),
                rsi_oversold=float(rsi_oversold),
                bollinger_period=int(bollinger_period),
                strength=float(strength),
            )
        )

    def on_candle(self, candle: Candle, balance: float) -> Signal | None:
        """Generate a long signal when price is stretched below the lower band."""

        history = self._append_candle(candle)
        if not history or len(history) < (
            max(self.params.bollinger_period, self.params.rsi_period) + 1
        ):
            return None
        closes = self.indicators.closes(history)
        previous = history[:-1]
        rsis = self.indicators.rsi(closes, self.params.rsi_period)
        bands = self.indicators.bollinger_bands(
            self.indicators.closes(previous),
            self.params.bollinger_period,
        )
        if not rsis or not bands:
            return None
        rsi_value = rsis[-1]
        _, _, lower_band = bands[-1]
        if candle.close <= lower_band and rsi_value <= self.params.rsi_oversold:
            return Signal(
                symbol=candle.symbol,
                asset_class=candle.asset_class,
                direction="long",
                strength=self.params.strength,
                entry_price=candle.close,
                sl_price=lower_band,
                tp_price=None,
                strategy_id=self.strategy_id,
                research_score=0.0,
            )
        return None
