"""Slice 5.9 trade-label time-decay tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ml.labels import (
    NO_EDGE_LABEL,
    PROFIT_TARGET_LABEL,
    STOP_LOSS_LABEL,
    TradeLabelConfig,
    barrier_health_report,
    build_long_trade_label_results,
)
from app.models.domain import Candle


def _candle(index: int, *, high: float, low: float, close: float = 100.0) -> Candle:
    return Candle(
        time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="1Day",
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
        source="unit_test",
    )


def test_fast_profit_target_has_more_weight_than_late_profit_target() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.01,
        stop_loss_pct=0.01,
        max_holding_candles=3,
        time_decay_min_weight=0.45,
        timeout_sample_weight=0.70,
    )
    candles = [
        _candle(0, high=100.0, low=100.0),
        _candle(1, high=101.5, low=100.0),
        _candle(2, high=100.0, low=100.0),
        _candle(3, high=101.5, low=100.0),
        _candle(4, high=100.0, low=100.0),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[0].label == PROFIT_TARGET_LABEL
    assert labels[0].bars_to_outcome == 1
    assert labels[1].label == PROFIT_TARGET_LABEL
    assert labels[1].bars_to_outcome == 2
    assert labels[0].time_decay_weight > labels[1].time_decay_weight


def test_timeout_is_no_edge_and_downweighted() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.02,
        stop_loss_pct=0.02,
        max_holding_candles=3,
        timeout_sample_weight=0.55,
    )
    candles = [
        _candle(0, high=100.5, low=99.5),
        _candle(1, high=100.5, low=99.5),
        _candle(2, high=100.5, low=99.5),
        _candle(3, high=100.5, low=99.5),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[0].label == NO_EDGE_LABEL
    assert labels[0].bars_to_outcome is None
    assert labels[0].time_decay_weight == 0.55


def test_stop_label_blocks_long_without_short_meaning() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.01,
        stop_loss_pct=0.01,
        max_holding_candles=3,
    )
    candles = [
        _candle(0, high=100.0, low=100.0),
        _candle(1, high=100.0, low=98.0),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[0].label == STOP_LOSS_LABEL
    assert labels[0].outcome_return < 0.0


def test_atr_barrier_uses_volatility_instead_of_fixed_percent() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.01,
        stop_loss_pct=0.01,
        max_holding_candles=2,
        use_atr_barriers=True,
        atr_period=1,
        profit_target_atr_multiplier=3.0,
        stop_loss_atr_multiplier=1.5,
    )
    candles = [
        _candle(0, high=101.0, low=99.0, close=100.0),
        _candle(1, high=101.0, low=99.0, close=100.0),
        _candle(2, high=102.0, low=99.5, close=101.0),
        _candle(3, high=102.0, low=99.5, close=101.0),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[1].label == NO_EDGE_LABEL


def test_atr_barrier_allows_larger_crypto_target() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.01,
        stop_loss_pct=0.01,
        max_holding_candles=2,
        use_atr_barriers=True,
        atr_period=1,
        profit_target_atr_multiplier=3.0,
        stop_loss_atr_multiplier=1.5,
    )
    candles = [
        _candle(0, high=101.0, low=99.0, close=100.0),
        _candle(1, high=101.0, low=99.0, close=100.0),
        _candle(2, high=106.1, low=99.5, close=105.0),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[1].label == PROFIT_TARGET_LABEL


def test_atr_barrier_uses_previous_bar_atr() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.01,
        stop_loss_pct=0.01,
        max_holding_candles=1,
        use_atr_barriers=True,
        atr_period=1,
        profit_target_atr_multiplier=1.0,
        stop_loss_atr_multiplier=1.0,
    )
    candles = [
        _candle(0, high=102.0, low=98.0, close=100.0),
        _candle(1, high=100.5, low=99.5, close=100.0),
        _candle(2, high=103.0, low=99.0, close=100.0),
    ]

    labels = build_long_trade_label_results(candles, config)

    assert labels[1].label == NO_EDGE_LABEL


def test_timeout_labels_respect_min_profitable_move() -> None:
    config = TradeLabelConfig(
        profit_target_pct=0.10,
        stop_loss_pct=0.10,
        max_holding_candles=1,
        min_profitable_move_pct=0.013,
    )

    small_move = build_long_trade_label_results(
        [
            _candle(0, high=100.0, low=100.0, close=100.0),
            _candle(1, high=101.2, low=101.2, close=101.2),
        ],
        config,
    )
    profitable_move = build_long_trade_label_results(
        [
            _candle(0, high=100.0, low=100.0, close=100.0),
            _candle(1, high=101.31, low=101.31, close=101.31),
        ],
        config,
    )
    losing_move = build_long_trade_label_results(
        [
            _candle(0, high=100.0, low=100.0, close=100.0),
            _candle(1, high=98.69, low=98.69, close=98.69),
        ],
        config,
    )

    assert small_move[0].label == NO_EDGE_LABEL
    assert profitable_move[0].label == PROFIT_TARGET_LABEL
    assert losing_move[0].label == STOP_LOSS_LABEL


def test_barrier_health_report_flags_unhealthy_hit_rates() -> None:
    healthy = barrier_health_report(
        [PROFIT_TARGET_LABEL] * 4 + [STOP_LOSS_LABEL] * 4 + [NO_EDGE_LABEL] * 2
    )
    unhealthy = barrier_health_report(
        [PROFIT_TARGET_LABEL] * 8 + [STOP_LOSS_LABEL] + [NO_EDGE_LABEL]
    )

    assert healthy["is_healthy"] is True
    assert healthy["tp_hit_rate"] == 0.4
    assert unhealthy["is_healthy"] is False
    assert "tp_hit_rate_above_0.45" in unhealthy["warnings"]
    assert "sl_hit_rate_below_0.30" in unhealthy["warnings"]
