"""ML-TF3 timeframe label behavior tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.ml.labels import (
    NO_EDGE_LABEL,
    PROFIT_TARGET_LABEL,
    TradeLabelConfig,
    TradeLabelResult,
    barrier_health_report,
    build_long_trade_label_results,
)
from app.ml.timeframe_config import get_trade_label_config
from app.ml.trainer import TrainerConfig, WalkForwardTrainer, _TrainingSample
from app.models.domain import Candle


def _candle(
    index: int,
    *,
    close: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    asset_class: str = "crypto",
    timeframe: str = "15m",
) -> Candle:
    return Candle(
        time=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * index),
        symbol="BTC/USD",
        asset_class=asset_class,
        timeframe=timeframe,
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=1000.0,
        source="test",
    )


def test_atr_barrier_uses_previous_bar_atr() -> None:
    """The label at bar N must use ATR from bar N-1, not bar N."""

    candles = [
        _candle(0, high=101.0, low=99.0),
        _candle(1, high=200.0, low=0.0),
        _candle(2, high=103.0, low=99.0, close=100.5),
    ]
    config = TradeLabelConfig(
        profit_target_pct=0.0,
        stop_loss_pct=0.0,
        max_holding_candles=1,
        use_atr_barriers=True,
        atr_period=1,
        profit_target_atr_multiplier=1.0,
        stop_loss_atr_multiplier=1.0,
    )

    results = build_long_trade_label_results(candles, config)

    assert results[1].label == PROFIT_TARGET_LABEL
    assert results[1].outcome_return == 0.02


def test_timeout_below_fee_aware_threshold_is_no_edge() -> None:
    candles = [
        _candle(0, close=100.0, high=101.0, low=99.0),
        _candle(1, close=101.0, high=101.0, low=100.0),
    ]
    config = TradeLabelConfig(
        profit_target_pct=0.10,
        stop_loss_pct=0.10,
        max_holding_candles=1,
        min_profitable_move_pct=0.013,
    )

    results = build_long_trade_label_results(candles, config)

    assert results[0].label == NO_EDGE_LABEL
    assert results[0].outcome_return == 0.01


def test_timeout_above_fee_aware_threshold_keeps_directional_label() -> None:
    candles = [
        _candle(0, close=100.0, high=101.0, low=99.0),
        _candle(1, close=102.0, high=102.0, low=100.0),
    ]
    config = TradeLabelConfig(
        profit_target_pct=0.10,
        stop_loss_pct=0.10,
        max_holding_candles=1,
        min_profitable_move_pct=0.013,
    )

    results = build_long_trade_label_results(candles, config)

    assert results[0].label == PROFIT_TARGET_LABEL
    assert results[0].outcome_return == 0.02


def test_per_timeframe_label_configs_match_contract() -> None:
    crypto_15m = get_trade_label_config("crypto", "15m")
    crypto_1h = get_trade_label_config("crypto", "1h")
    crypto_4h = get_trade_label_config("crypto", "4h")
    stock_5m = get_trade_label_config("stock", "5m")
    stock_15m = get_trade_label_config("stock", "15m")
    stock_1h = get_trade_label_config("stock", "1h")
    stock_4h = get_trade_label_config("stock", "4h")

    assert crypto_15m.use_atr_barriers is True
    assert crypto_15m.profit_target_atr_multiplier == 1.8
    assert crypto_15m.stop_loss_atr_multiplier == 1.1
    assert crypto_15m.max_holding_candles == 6
    assert crypto_15m.min_profitable_move_pct == 0.013

    assert crypto_1h.profit_target_atr_multiplier == 2.2
    assert crypto_1h.stop_loss_atr_multiplier == 1.4
    assert crypto_1h.max_holding_candles == 8

    assert crypto_4h.use_atr_barriers is False
    assert crypto_4h.profit_target_pct == 0.035
    assert crypto_4h.stop_loss_pct == 0.022
    assert crypto_4h.max_holding_candles == 6

    assert stock_5m.profit_target_atr_multiplier == 1.6
    assert stock_5m.stop_loss_atr_multiplier == 1.0
    assert stock_5m.max_holding_candles == 12
    assert stock_5m.min_profitable_move_pct == 0.002

    assert stock_15m.profit_target_atr_multiplier == 1.8
    assert stock_15m.stop_loss_atr_multiplier == 1.1
    assert stock_15m.max_holding_candles == 8

    assert stock_1h.profit_target_atr_multiplier == 2.0
    assert stock_1h.stop_loss_atr_multiplier == 1.2
    assert stock_1h.max_holding_candles == 6

    assert stock_4h.use_atr_barriers is False
    assert stock_4h.profit_target_pct == 0.020
    assert stock_4h.stop_loss_pct == 0.012
    assert stock_4h.max_holding_candles == 4


def test_barrier_health_report_warns_outside_target_bands() -> None:
    results = [
        TradeLabelResult(PROFIT_TARGET_LABEL, 1, 0.02, 1.0),
        TradeLabelResult(PROFIT_TARGET_LABEL, 1, 0.02, 1.0),
        TradeLabelResult(PROFIT_TARGET_LABEL, 1, 0.02, 1.0),
        TradeLabelResult(NO_EDGE_LABEL, None, 0.0, 0.7),
    ]

    report = barrier_health_report(results)

    assert report["tp_hit_rate"] == 0.75
    assert report["is_healthy"] is False
    assert report["warnings"]


def test_walk_forward_purges_training_rows_before_validation() -> None:
    trainer = WalkForwardTrainer(TrainerConfig())
    start = datetime(2026, 1, 1, tzinfo=UTC)
    train_samples = [
        _TrainingSample(
            timestamp=start + timedelta(days=index),
            month_key=(2026, 1),
            features={},
            label=NO_EDGE_LABEL,
            next_return=0.0,
            symbol="BTC/USD",
            label_horizon_bars=3,
        )
        for index in range(10)
    ]
    test_samples = [
        _TrainingSample(
            timestamp=start + timedelta(days=10),
            month_key=(2026, 2),
            features={},
            label=NO_EDGE_LABEL,
            next_return=0.0,
            symbol="BTC/USD",
            label_horizon_bars=3,
        )
    ]

    purged_train, embargoed_test = trainer._apply_purge_and_embargo(
        train_samples,
        test_samples,
    )

    assert len(purged_train) == 7
    assert purged_train[-1].timestamp == start + timedelta(days=6)
    assert embargoed_test == test_samples
