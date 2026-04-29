"""Trade-outcome label builders for ML training."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.domain import Candle

STOP_LOSS_LABEL = 0
NO_EDGE_LABEL = 1
PROFIT_TARGET_LABEL = 2


@dataclass(slots=True, frozen=True)
class TradeLabelConfig:
    """Triple-barrier labeling settings."""

    profit_target_pct: float
    stop_loss_pct: float
    max_holding_candles: int
    time_decay_min_weight: float = 0.45
    timeout_sample_weight: float = 0.70
    use_atr_barriers: bool = False
    atr_period: int = 14
    profit_target_atr_multiplier: float = 3.0
    stop_loss_atr_multiplier: float = 1.5


@dataclass(slots=True, frozen=True)
class TradeLabelResult:
    """One triple-barrier label plus training weight diagnostics."""

    label: int
    bars_to_outcome: int | None
    outcome_return: float
    time_decay_weight: float


def build_long_trade_labels(
    candles: Sequence[Candle],
    config: TradeLabelConfig,
) -> list[int]:
    """Label candles by long trade outcome.

    Labels keep the existing multiclass contract:
    0 = stop hit first, 1 = timeout/unclear/no edge, 2 = profit hit first.
    A negative crypto label means suppress/block a long entry only. It never means short.
    """

    return [result.label for result in build_long_trade_label_results(candles, config)]


def build_long_trade_label_results(
    candles: Sequence[Candle],
    config: TradeLabelConfig,
) -> list[TradeLabelResult]:
    """Build long-only triple-barrier labels with optional ATR barriers.

    ATR barriers adapt the TP/SL distance to the symbol's recent volatility.
    Fast target/stop hits carry stronger weights. Late outcomes decay softly so
    valid crypto moves are not punished as aggressively as the 5.9 linear decay.
    """

    labels: list[TradeLabelResult] = []
    lookahead = max(1, config.max_holding_candles)
    atr_values = _average_true_ranges(candles, config.atr_period)

    for index, candle in enumerate(candles):
        entry = candle.close
        if entry <= 0.0 or index >= len(candles) - 1:
            labels.append(
                TradeLabelResult(
                    label=NO_EDGE_LABEL,
                    bars_to_outcome=None,
                    outcome_return=0.0,
                    time_decay_weight=_bounded_timeout_weight(config),
                )
            )
            continue

        target_price, stop_price = _barrier_prices(
            entry_price=entry,
            atr_value=atr_values[index],
            config=config,
        )
        future_window = candles[index + 1 : index + 1 + lookahead]
        labels.append(
            _first_barrier_result(
                future_window,
                entry_price=entry,
                target_price=target_price,
                stop_price=stop_price,
                lookahead=lookahead,
                config=config,
            )
        )

    return labels


def label_balance_report(labels: Sequence[int]) -> dict[str, object]:
    """Return compact class balance diagnostics for model/result payloads."""

    counts = {STOP_LOSS_LABEL: 0, NO_EDGE_LABEL: 0, PROFIT_TARGET_LABEL: 0}
    for label in labels:
        counts[int(label)] = counts.get(int(label), 0) + 1

    total = len(labels)
    ratios = {
        str(label): (count / total if total > 0 else 0.0)
        for label, count in counts.items()
    }
    return {
        "total": total,
        "counts": counts,
        "ratios": ratios,
        "label_meanings": {
            "0": "stop_hit_first_block_long",
            "1": "timeout_or_unclear_no_edge",
            "2": "profit_target_hit_first_allow_long_bias",
        },
    }


def _barrier_prices(
    *,
    entry_price: float,
    atr_value: float | None,
    config: TradeLabelConfig,
) -> tuple[float, float]:
    """Return target and stop prices using ATR barriers when available."""

    if config.use_atr_barriers and atr_value is not None and atr_value > 0.0:
        target_distance = atr_value * max(0.01, config.profit_target_atr_multiplier)
        stop_distance = atr_value * max(0.01, config.stop_loss_atr_multiplier)
        return entry_price + target_distance, max(0.0, entry_price - stop_distance)

    return (
        entry_price * (1.0 + config.profit_target_pct),
        entry_price * (1.0 - config.stop_loss_pct),
    )


def _average_true_ranges(
    candles: Sequence[Candle],
    period: int,
) -> list[float | None]:
    """Return ATR values aligned to the input candles."""

    bounded_period = max(1, period)
    true_ranges: list[float] = []
    atr_values: list[float | None] = []
    previous_close: float | None = None

    for candle in candles:
        high_low = max(0.0, candle.high - candle.low)
        if previous_close is None:
            true_range = high_low
        else:
            true_range = max(
                high_low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = candle.close

        if len(true_ranges) < bounded_period:
            atr_values.append(None)
            continue

        window = true_ranges[-bounded_period:]
        atr_values.append(sum(window) / bounded_period)

    return atr_values


def _first_barrier_result(
    future_window: Sequence[Candle],
    *,
    entry_price: float,
    target_price: float,
    stop_price: float,
    lookahead: int,
    config: TradeLabelConfig,
) -> TradeLabelResult:
    """Return the first barrier reached in the lookahead window."""

    for offset, future in enumerate(future_window, start=1):
        hit_target = future.high >= target_price
        hit_stop = future.low <= stop_price
        if hit_target and hit_stop:
            return TradeLabelResult(
                label=NO_EDGE_LABEL,
                bars_to_outcome=offset,
                outcome_return=0.0,
                time_decay_weight=_bounded_timeout_weight(config),
            )
        if hit_target:
            return TradeLabelResult(
                label=PROFIT_TARGET_LABEL,
                bars_to_outcome=offset,
                outcome_return=(target_price - entry_price) / entry_price,
                time_decay_weight=_time_decay_weight(offset, lookahead, config),
            )
        if hit_stop:
            return TradeLabelResult(
                label=STOP_LOSS_LABEL,
                bars_to_outcome=offset,
                outcome_return=(stop_price - entry_price) / entry_price,
                time_decay_weight=_time_decay_weight(offset, lookahead, config),
            )
    return TradeLabelResult(
        label=NO_EDGE_LABEL,
        bars_to_outcome=None,
        outcome_return=0.0,
        time_decay_weight=_bounded_timeout_weight(config),
    )


def _time_decay_weight(
    bars_to_outcome: int,
    lookahead: int,
    config: TradeLabelConfig,
) -> float:
    """Return a soft bounded decay from fast outcomes to late outcomes."""

    minimum = min(1.0, max(0.05, config.time_decay_min_weight))
    if lookahead <= 0:
        return 1.0

    soft_weight = 1.0 / (1.0 + (max(1, bars_to_outcome) / lookahead))
    return max(minimum, soft_weight)


def _bounded_timeout_weight(config: TradeLabelConfig) -> float:
    return min(1.0, max(0.05, config.timeout_sample_weight))
