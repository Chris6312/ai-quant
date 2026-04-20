"""Pure-Python indicator calculations used by the strategy layer."""

from __future__ import annotations

from collections.abc import Sequence
from math import sqrt

from app.models.domain import Candle


class IndicatorLib:
    """Compute vectorized-style indicators from candle sequences."""

    def closes(self, candles: Sequence[Candle]) -> list[float]:
        """Return candle closes."""

        return [candle.close for candle in candles]

    def highs(self, candles: Sequence[Candle]) -> list[float]:
        """Return candle highs."""

        return [candle.high for candle in candles]

    def lows(self, candles: Sequence[Candle]) -> list[float]:
        """Return candle lows."""

        return [candle.low for candle in candles]

    def volumes(self, candles: Sequence[Candle]) -> list[float]:
        """Return candle volumes."""

        return [candle.volume for candle in candles]

    def ema(self, values: Sequence[float], period: int) -> list[float]:
        """Return the exponential moving average series."""

        if period <= 0:
            raise ValueError("EMA period must be positive")
        if not values:
            return []
        alpha = 2.0 / (period + 1.0)
        ema_values = [float(values[0])]
        for value in values[1:]:
            ema_values.append((float(value) * alpha) + (ema_values[-1] * (1.0 - alpha)))
        return ema_values

    def sma(self, values: Sequence[float], period: int) -> list[float]:
        """Return the simple moving average series."""

        if period <= 0:
            raise ValueError("SMA period must be positive")
        if len(values) < period:
            return []
        result: list[float] = []
        window_sum = sum(float(value) for value in values[:period])
        result.append(window_sum / period)
        for index in range(period, len(values)):
            window_sum += float(values[index]) - float(values[index - period])
            result.append(window_sum / period)
        return result

    def rsi(self, values: Sequence[float], period: int = 14) -> list[float]:
        """Return the RSI series."""

        if period <= 0:
            raise ValueError("RSI period must be positive")
        if len(values) <= period:
            return []
        gains: list[float] = []
        losses: list[float] = []
        for index in range(1, len(values)):
            change = float(values[index]) - float(values[index - 1])
            gains.append(max(0.0, change))
            losses.append(max(0.0, -change))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rsis: list[float] = []
        for index in range(period, len(gains)):
            avg_gain = ((avg_gain * (period - 1)) + gains[index]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[index]) / period
            if avg_loss == 0.0:
                rsis.append(100.0)
                continue
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
        return rsis

    def atr(self, candles: Sequence[Candle], period: int = 14) -> list[float]:
        """Return the ATR series."""

        if period <= 0:
            raise ValueError("ATR period must be positive")
        if len(candles) <= period:
            return []
        true_ranges: list[float] = []
        previous_close = candles[0].close
        for candle in candles[1:]:
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
            true_ranges.append(true_range)
            previous_close = candle.close
        if len(true_ranges) < period:
            return []
        atr_values: list[float] = []
        atr_current = sum(true_ranges[:period]) / period
        atr_values.append(atr_current)
        for true_range in true_ranges[period:]:
            atr_current = ((atr_current * (period - 1)) + true_range) / period
            atr_values.append(atr_current)
        return atr_values

    def bollinger_bands(
        self,
        values: Sequence[float],
        period: int = 20,
        stdev_mult: float = 2.0,
    ) -> list[tuple[float, float, float]]:
        """Return Bollinger band tuples (middle, upper, lower)."""

        if period <= 0:
            raise ValueError("Bollinger period must be positive")
        if len(values) < period:
            return []
        bands: list[tuple[float, float, float]] = []
        for index in range(period, len(values) + 1):
            window = [float(value) for value in values[index - period : index]]
            mean = sum(window) / period
            variance = sum((value - mean) ** 2 for value in window) / period
            deviation = sqrt(variance)
            bands.append((mean, mean + stdev_mult * deviation, mean - stdev_mult * deviation))
        return bands

    def vwap(self, candles: Sequence[Candle]) -> float:
        """Return the volume weighted average price."""

        total_volume = sum(candle.volume for candle in candles)
        if total_volume == 0.0:
            return 0.0
        total_price_volume = sum(candle.close * candle.volume for candle in candles)
        return total_price_volume / total_volume

    def average_volume(self, candles: Sequence[Candle], period: int = 20) -> float:
        """Return the average volume of the last `period` candles."""

        if period <= 0:
            raise ValueError("Volume period must be positive")
        if len(candles) < period:
            return 0.0
        window = candles[-period:]
        return sum(candle.volume for candle in window) / period

    def adx(self, candles: Sequence[Candle], period: int = 14) -> float:
        """Return a simplified ADX value for the latest window."""

        if len(candles) <= period:
            return 0.0
        highs = self.highs(candles)
        lows = self.lows(candles)
        closes = self.closes(candles)
        plus_dm: list[float] = []
        minus_dm: list[float] = []
        tr_values: list[float] = []
        for index in range(1, len(candles)):
            up_move = highs[index] - highs[index - 1]
            down_move = lows[index - 1] - lows[index]
            plus_dm.append(up_move if up_move > down_move and up_move > 0.0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0.0 else 0.0)
            tr_values.append(
                max(
                    highs[index] - lows[index],
                    abs(highs[index] - closes[index - 1]),
                    abs(lows[index] - closes[index - 1]),
                )
            )
        if len(tr_values) < period:
            return 0.0
        atr = sum(tr_values[:period]) / period
        if atr == 0.0:
            return 0.0
        plus_di = 100.0 * (sum(plus_dm[:period]) / period) / atr
        minus_di = 100.0 * (sum(minus_dm[:period]) / period) / atr
        if plus_di + minus_di == 0.0:
            return 0.0
        dx = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx
