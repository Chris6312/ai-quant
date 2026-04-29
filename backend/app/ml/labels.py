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
    """Build long-only triple-barrier labels with TP/SL time-decay weights.

    Fast target/stop hits carry full weight. Late target/stop hits decay toward
    ``time_decay_min_weight`` so slow, noisy outcomes do not dominate training.
    Timeouts remain the neutral/no-edge class and are down-weighted separately.
    """

    labels: list[TradeLabelResult] = []
    lookahead = max(1, config.max_holding_candles)

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

        target_price = entry * (1.0 + config.profit_target_pct)
        stop_price = entry * (1.0 - config.stop_loss_pct)
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
    """Return a bounded linear decay from fast outcomes to late outcomes."""

    minimum = min(1.0, max(0.05, config.time_decay_min_weight))
    if lookahead <= 1:
        return 1.0
    progress = (max(1, bars_to_outcome) - 1) / (lookahead - 1)
    return max(minimum, 1.0 - ((1.0 - minimum) * progress))


def _bounded_timeout_weight(config: TradeLabelConfig) -> float:
    return min(1.0, max(0.05, config.timeout_sample_weight))
