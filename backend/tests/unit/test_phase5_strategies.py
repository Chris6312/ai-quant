"""Tests for Phase 5 signal generation and strategy registry modules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.indicators.library import IndicatorLib
from app.models.domain import Candle
from app.signals.registry import StrategyRegistry
from app.strategies.breakout import BreakoutStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.momentum import MomentumStrategy
from app.strategies.vwap import VWAPStrategy

BASE_TIME = datetime(2026, 4, 18, 14, 30, tzinfo=UTC)


def make_candle(close: float, *, minutes: int, volume: float = 1_000.0) -> Candle:
    """Create a candle with a predictable timestamp and OHLC structure."""

    return Candle(
        time=BASE_TIME + timedelta(minutes=minutes),
        symbol="AAPL",
        asset_class="stock",
        timeframe="1Day",
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
        source="tradier",
    )


def build_trending_history() -> list[Candle]:
    """Build a history that trends down and then strongly up."""

    down = [make_candle(100.0 - index, minutes=index) for index in range(25)]
    up = [make_candle(76.0 + index, minutes=25 + index) for index in range(25)]
    return down + up


def build_flat_history() -> list[Candle]:
    """Build a stable price history for reversal-style strategies."""

    return [make_candle(100.0, minutes=index) for index in range(30)]


def build_breakout_history() -> list[Candle]:
    """Build a flat range followed by a breakout candle."""

    base = [make_candle(100.0, minutes=index) for index in range(25)]
    breakout = make_candle(106.0, minutes=25, volume=5_000.0)
    return [*base, breakout]


def test_indicator_lib_calculates_core_values() -> None:
    """Indicator helpers should return non-empty values for valid history."""

    history = build_trending_history()
    lib = IndicatorLib()
    closes = lib.closes(history)
    assert lib.ema(closes, 8)
    assert lib.rsi(closes, 14)
    assert lib.bollinger_bands(closes, 20)
    assert lib.vwap(history) > 0.0
    assert lib.average_volume(history, 20) > 0.0
    assert lib.adx(history, 14) >= 0.0


def test_strategy_registry_builds_enabled_strategies() -> None:
    """The registry should build all enabled strategy instances."""

    registry = StrategyRegistry.from_mapping(
        {
            "strategies": [
                {"name": "momentum", "enabled": True, "params": {}},
                {"name": "mean_reversion", "enabled": True, "params": {}},
                {"name": "vwap", "enabled": False, "params": {}},
                {"name": "breakout", "enabled": True, "params": {}},
            ]
        }
    )
    strategies = registry.build_enabled_strategies()
    assert [strategy.strategy_id for strategy in strategies] == [
        "momentum",
        "mean_reversion",
        "breakout",
    ]


def test_momentum_strategy_emits_long_signal() -> None:
    """Momentum should emit a long signal on a bullish EMA crossover."""

    strategy = MomentumStrategy()
    history = build_trending_history()
    strategy.seed_history(history[:-1])
    signal = strategy.on_candle(history[-1], balance=10_000.0)
    assert signal is not None
    assert signal.direction == "long"
    assert signal.strategy_id == "momentum"


def test_mean_reversion_strategy_emits_long_signal() -> None:
    """Mean reversion should emit a long signal when price is oversold."""

    strategy = MeanReversionStrategy()
    history = build_flat_history()
    oversold = make_candle(90.0, minutes=30)
    strategy.seed_history(history)
    signal = strategy.on_candle(oversold, balance=10_000.0)
    assert signal is not None
    assert signal.direction == "long"
    assert signal.strategy_id == "mean_reversion"


def test_vwap_strategy_emits_long_signal() -> None:
    """VWAP deviation should emit a long signal below the lower band."""

    strategy = VWAPStrategy()
    history = build_flat_history()
    oversold = make_candle(90.0, minutes=30)
    strategy.seed_history(history)
    signal = strategy.on_candle(oversold, balance=10_000.0)
    assert signal is not None
    assert signal.direction == "long"
    assert signal.strategy_id == "vwap"


def test_breakout_strategy_emits_long_signal() -> None:
    """Breakout should emit a long signal on new highs with volume expansion."""

    strategy = BreakoutStrategy()
    history = build_breakout_history()
    strategy.seed_history(history[:-1])
    signal = strategy.on_candle(history[-1], balance=10_000.0)
    assert signal is not None
    assert signal.direction == "long"
    assert signal.strategy_id == "breakout"
