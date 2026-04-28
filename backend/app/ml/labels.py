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


def build_long_trade_labels(
    candles: Sequence[Candle],
    config: TradeLabelConfig,
) -> list[int]:
    """Label candles by long trade outcome.

    Labels keep the existing multiclass contract:
    0 = stop hit first, 1 = timeout/unclear/no edge, 2 = profit hit first.
    A negative crypto label means suppress/block a long entry only. It never means short.
    """

    labels: list[int] = []
    lookahead = max(1, config.max_holding_candles)

    for index, candle in enumerate(candles):
        entry = candle.close
        if entry <= 0.0 or index >= len(candles) - 1:
            labels.append(NO_EDGE_LABEL)
            continue

        target_price = entry * (1.0 + config.profit_target_pct)
        stop_price = entry * (1.0 - config.stop_loss_pct)
        future_window = candles[index + 1 : index + 1 + lookahead]
        labels.append(_first_barrier_label(future_window, target_price, stop_price))

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


def _first_barrier_label(
    future_window: Sequence[Candle],
    target_price: float,
    stop_price: float,
) -> int:
    """Return the first barrier reached in the lookahead window."""

    for future in future_window:
        hit_target = future.high >= target_price
        hit_stop = future.low <= stop_price
        if hit_target and hit_stop:
            return NO_EDGE_LABEL
        if hit_target:
            return PROFIT_TARGET_LABEL
        if hit_stop:
            return STOP_LOSS_LABEL
    return NO_EDGE_LABEL
