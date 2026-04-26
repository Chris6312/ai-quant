"""Closed-candle intraday technical confirmation for Phase 9.1.

The decision layer uses this module as live eyes. It reads already-persisted
trading candles and summarizes 15m, 1h, and 4h structure without fetching open
candles, mutating broker state, or executing trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from app.config.constants import TRADING_CANDLE_USAGE
from app.db.models import CandleRow
from app.decision.visibility import IntradayConfirmation, IntradayTrend, VolatilityState
from app.repositories.candles import CandleRepository

INTRADAY_DECISION_TIMEFRAMES: Final[tuple[str, ...]] = ("15m", "1h", "4h")
DEFAULT_CANDLE_LIMIT: Final[int] = 60
TREND_FAST_PERIOD: Final[int] = 5
TREND_SLOW_PERIOD: Final[int] = 20
BREAKOUT_LOOKBACK: Final[int] = 20
VOLUME_LOOKBACK: Final[int] = 20
VOLUME_EXPANSION_MULTIPLIER: Final[float] = 1.5
VOLATILITY_EXPANDED_MULTIPLIER: Final[float] = 1.5
VOLATILITY_COMPRESSED_MULTIPLIER: Final[float] = 0.7


@dataclass(frozen=True, slots=True)
class TimeframeTechnicalSnapshot:
    """Technical proof summary for one closed intraday timeframe."""

    timeframe: str
    trend: IntradayTrend
    breakout: bool
    volume_expansion: bool
    volatility_state: VolatilityState
    candle_count: int
    latest_candle_time: datetime | None


@dataclass(frozen=True, slots=True)
class IntradayTechnicalSnapshot:
    """Aggregate closed-candle technical snapshot across intraday timeframes."""

    confirmation: IntradayConfirmation
    timeframe_snapshots: tuple[TimeframeTechnicalSnapshot, ...]


async def build_intraday_snapshot_from_repository(
    repository: CandleRepository,
    symbol: str,
    *,
    timeframes: tuple[str, ...] = INTRADAY_DECISION_TIMEFRAMES,
    candle_limit: int = DEFAULT_CANDLE_LIMIT,
) -> IntradayTechnicalSnapshot:
    """Build an intraday snapshot from persisted trading-lane candles.

    Persisted trading candles are treated as closed candles. The caller should run
    this after the candle-close worker has written 15m, 1h, or 4h data.
    """

    if candle_limit <= 0:
        raise ValueError("candle_limit must be positive")

    candles_by_timeframe: dict[str, list[CandleRow]] = {}
    for timeframe in timeframes:
        rows = await repository.list_recent(
            symbol=symbol,
            timeframe=timeframe,
            limit=candle_limit,
            usage=TRADING_CANDLE_USAGE,
        )
        candles_by_timeframe[timeframe] = rows
    return build_intraday_snapshot(candles_by_timeframe)


def build_intraday_snapshot(
    candles_by_timeframe: dict[str, list[CandleRow]],
) -> IntradayTechnicalSnapshot:
    """Build a closed-candle intraday technical snapshot from candle rows."""

    timeframe_snapshots = tuple(
        _build_timeframe_snapshot(timeframe, rows)
        for timeframe, rows in candles_by_timeframe.items()
    )
    proof_timeframes = [
        snapshot.timeframe
        for snapshot in timeframe_snapshots
        if _has_technical_proof(snapshot)
    ]
    confirmation = IntradayConfirmation(
        trend=_aggregate_trend(timeframe_snapshots),
        breakout=any(snapshot.breakout for snapshot in timeframe_snapshots),
        volume_expansion=any(snapshot.volume_expansion for snapshot in timeframe_snapshots),
        volatility_state=_aggregate_volatility(timeframe_snapshots),
        timeframes=proof_timeframes,
        as_of=_latest_snapshot_time(timeframe_snapshots),
    )
    return IntradayTechnicalSnapshot(
        confirmation=confirmation,
        timeframe_snapshots=timeframe_snapshots,
    )


def _build_timeframe_snapshot(
    timeframe: str,
    rows: list[CandleRow],
) -> TimeframeTechnicalSnapshot:
    ordered_rows = sorted(rows, key=lambda row: row.time)
    complete_rows = [row for row in ordered_rows if _has_required_ohlcv(row)]
    candle_count = len(complete_rows)
    latest_candle_time = complete_rows[-1].time if complete_rows else None
    if candle_count < TREND_SLOW_PERIOD:
        return TimeframeTechnicalSnapshot(
            timeframe=timeframe,
            trend="unknown",
            breakout=False,
            volume_expansion=False,
            volatility_state="unknown",
            candle_count=candle_count,
            latest_candle_time=latest_candle_time,
        )

    closes = [_to_float(row.close) for row in complete_rows]
    highs = [_to_float(row.high) for row in complete_rows]
    volumes = [_to_float(row.volume) for row in complete_rows]
    trend = _classify_trend(closes)
    return TimeframeTechnicalSnapshot(
        timeframe=timeframe,
        trend=trend,
        breakout=_is_breakout(closes=closes, highs=highs),
        volume_expansion=_has_volume_expansion(volumes),
        volatility_state=_classify_volatility(complete_rows),
        candle_count=candle_count,
        latest_candle_time=latest_candle_time,
    )


def _has_required_ohlcv(row: CandleRow) -> bool:
    return (
        row.open is not None
        and row.high is not None
        and row.low is not None
        and row.close is not None
        and row.volume is not None
    )


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        raise ValueError("candle value cannot be None after completeness filtering")
    return float(value)


def _classify_trend(closes: list[float]) -> IntradayTrend:
    fast_mean = _mean(closes[-TREND_FAST_PERIOD:])
    slow_mean = _mean(closes[-TREND_SLOW_PERIOD:])
    latest_close = closes[-1]
    if latest_close > slow_mean and fast_mean > slow_mean:
        return "bullish"
    if latest_close < slow_mean and fast_mean < slow_mean:
        return "bearish"
    return "neutral"


def _is_breakout(*, closes: list[float], highs: list[float]) -> bool:
    if len(closes) <= BREAKOUT_LOOKBACK:
        return False
    prior_high = max(highs[-BREAKOUT_LOOKBACK - 1 : -1])
    return closes[-1] > prior_high


def _has_volume_expansion(volumes: list[float]) -> bool:
    if len(volumes) <= VOLUME_LOOKBACK:
        return False
    prior_average = _mean(volumes[-VOLUME_LOOKBACK - 1 : -1])
    if prior_average <= 0.0:
        return False
    return volumes[-1] >= prior_average * VOLUME_EXPANSION_MULTIPLIER


def _classify_volatility(rows: list[CandleRow]) -> VolatilityState:
    if len(rows) <= VOLUME_LOOKBACK:
        return "unknown"
    ranges = [_to_float(row.high) - _to_float(row.low) for row in rows]
    prior_average = _mean(ranges[-VOLUME_LOOKBACK - 1 : -1])
    latest_range = ranges[-1]
    if prior_average <= 0.0:
        return "unknown"
    if latest_range >= prior_average * VOLATILITY_EXPANDED_MULTIPLIER:
        return "expanded"
    if latest_range <= prior_average * VOLATILITY_COMPRESSED_MULTIPLIER:
        return "compressed"
    return "normal"


def _aggregate_trend(snapshots: tuple[TimeframeTechnicalSnapshot, ...]) -> IntradayTrend:
    bullish_count = sum(1 for snapshot in snapshots if snapshot.trend == "bullish")
    bearish_count = sum(1 for snapshot in snapshots if snapshot.trend == "bearish")
    if bullish_count >= 2 and bearish_count == 0:
        return "bullish"
    if bearish_count >= 2 and bullish_count == 0:
        return "bearish"
    if bullish_count > 0 and bearish_count > 0:
        return "mixed"
    if bullish_count == 1:
        return "bullish"
    if bearish_count == 1:
        return "bearish"
    if any(snapshot.trend == "neutral" for snapshot in snapshots):
        return "neutral"
    return "unknown"


def _aggregate_volatility(
    snapshots: tuple[TimeframeTechnicalSnapshot, ...],
) -> VolatilityState:
    states = [snapshot.volatility_state for snapshot in snapshots]
    if "expanded" in states:
        return "expanded"
    if "compressed" in states:
        return "compressed"
    if "normal" in states:
        return "normal"
    return "unknown"


def _latest_snapshot_time(snapshots: tuple[TimeframeTechnicalSnapshot, ...]) -> datetime | None:
    latest_times = [
        snapshot.latest_candle_time
        for snapshot in snapshots
        if snapshot.latest_candle_time is not None
    ]
    if not latest_times:
        return None
    return max(latest_times)


def _has_technical_proof(snapshot: TimeframeTechnicalSnapshot) -> bool:
    return (
        snapshot.trend in {"bullish", "bearish"}
        or snapshot.breakout
        or snapshot.volume_expansion
        or snapshot.volatility_state in {"expanded", "compressed"}
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)
