"""Phase S5 stock screener worker orchestration.

This worker builds the stock universe, creates deterministic local stub
snapshots, screens each candidate, and persists candidate rows. It does not
fetch provider data, rank candidates, or make strategy/trading decisions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.db.stock_models import StockUniverseCandidateRow
from app.stock.universe import StockUniverseCandidate, build_stock_universe
from app.stock.validation import (
    StockEarningsRiskSnapshot,
    StockLiquiditySnapshot,
    StockScreeningResult,
    StockScreeningThresholds,
    StockTradabilitySnapshot,
    screen_stock_candidate,
)
from app.tasks.worker import celery_app

STOCK_SCREENER_TASK_NAME = "tasks.stock_screener.run"


@dataclass(frozen=True, slots=True)
class StockScreenerRunResult:
    """Summary of one stock screener worker run."""

    as_of: datetime
    candidate_count: int
    passed_count: int
    failed_count: int
    persisted_count: int
    rows: tuple[StockUniverseCandidateRow, ...]


@dataclass(frozen=True, slots=True)
class StockScreenerStubSnapshot:
    """Local deterministic placeholder inputs for S5 validation only."""

    liquidity_snapshot: StockLiquiditySnapshot
    tradability_snapshot: StockTradabilitySnapshot
    earnings_risk_snapshot: StockEarningsRiskSnapshot
    sector: str


@celery_app.task(name=STOCK_SCREENER_TASK_NAME)
def stock_screener_task(
    sp500: list[str] | None = None,
    nasdaq100: list[str] | None = None,
    high_volume: list[str] | None = None,
    manual: list[str] | None = None,
    event_driven: list[str] | None = None,
    as_of: str | None = None,
) -> dict[str, object]:
    """Run the S5 stock screener worker from Celery."""

    parsed_as_of = datetime.fromisoformat(as_of) if as_of is not None else None
    result = asyncio.run(
        run_stock_screener(
            sp500=sp500 or (),
            nasdaq100=nasdaq100 or (),
            high_volume=high_volume or (),
            manual=manual or (),
            event_driven=event_driven or (),
            as_of=parsed_as_of,
        )
    )
    return {
        "status": "ok",
        "task": "stock_screener",
        "asset_class": "stock",
        "candidate_count": result.candidate_count,
        "passed_count": result.passed_count,
        "failed_count": result.failed_count,
        "persisted_count": result.persisted_count,
        "as_of": result.as_of.isoformat(),
        "symbols": [row.symbol for row in result.rows],
    }


async def run_stock_screener(
    *,
    sp500: Sequence[str] = (),
    nasdaq100: Sequence[str] = (),
    high_volume: Sequence[str] = (),
    manual: Sequence[str] = (),
    event_driven: Sequence[str] = (),
    thresholds: StockScreeningThresholds | None = None,
    as_of: datetime | None = None,
    session_factory: async_sessionmaker[Any] | None = None,
) -> StockScreenerRunResult:
    """Build, screen, and persist the stock universe candidate rows."""

    active_thresholds = thresholds or StockScreeningThresholds()
    effective_as_of = _coerce_utc_as_of(as_of)
    candidates = build_stock_universe(
        sp500=sp500,
        nasdaq100=nasdaq100,
        high_volume=high_volume,
        manual=manual,
        event_driven=event_driven,
    )
    rows = tuple(
        _candidate_to_row(
            candidate=candidate,
            thresholds=active_thresholds,
            as_of=effective_as_of,
        )
        for candidate in candidates
    )
    await _persist_candidate_rows(rows, session_factory=session_factory)

    passed_count = sum(1 for row in rows if row.reason == "pass")
    return StockScreenerRunResult(
        as_of=effective_as_of,
        candidate_count=len(candidates),
        passed_count=passed_count,
        failed_count=len(candidates) - passed_count,
        persisted_count=len(rows),
        rows=rows,
    )


def _candidate_to_row(
    *,
    candidate: StockUniverseCandidate,
    thresholds: StockScreeningThresholds,
    as_of: datetime,
) -> StockUniverseCandidateRow:
    snapshot = build_stub_stock_screener_snapshot(
        candidate=candidate,
        thresholds=thresholds,
    )
    result = screen_stock_candidate(
        candidate=candidate,
        thresholds=thresholds,
        liquidity_snapshot=snapshot.liquidity_snapshot,
        tradability_snapshot=snapshot.tradability_snapshot,
        earnings_risk_snapshot=snapshot.earnings_risk_snapshot,
        sector=snapshot.sector,
    )
    return build_stock_universe_candidate_row(
        candidate=candidate,
        result=result,
        as_of=as_of,
    )


def build_stub_stock_screener_snapshot(
    *,
    candidate: StockUniverseCandidate,
    thresholds: StockScreeningThresholds,
) -> StockScreenerStubSnapshot:
    """Build deterministic S5-only validation inputs for one candidate."""

    price = _stub_price(thresholds)
    spread_ratio = _stub_spread_ratio(thresholds)
    bid = price * (1 - spread_ratio / 2)
    ask = price * (1 + spread_ratio / 2)
    unsupported_reason = candidate.unsupported_reason or "symbol is unsupported"
    return StockScreenerStubSnapshot(
        liquidity_snapshot=StockLiquiditySnapshot(
            symbol=candidate.symbol,
            price=price,
            average_daily_volume=_stub_above_threshold(
                thresholds.min_average_daily_volume
            ),
            dollar_volume=_stub_above_threshold(thresholds.min_dollar_volume),
            bid=bid,
            ask=ask,
        ),
        tradability_snapshot=StockTradabilitySnapshot(
            symbol=candidate.symbol,
            is_tradable=candidate.is_supported,
            reason=None if candidate.is_supported else unsupported_reason,
        ),
        earnings_risk_snapshot=StockEarningsRiskSnapshot(
            symbol=candidate.symbol,
            is_in_danger_window=False,
        ),
        sector="Unclassified",
    )


def build_stock_universe_candidate_row(
    *,
    candidate: StockUniverseCandidate,
    result: StockScreeningResult,
    as_of: datetime,
) -> StockUniverseCandidateRow:
    """Convert a screening result into the S2 candidate table shape."""

    return StockUniverseCandidateRow(
        id=str(uuid4()),
        symbol=candidate.symbol,
        source=_candidate_source(candidate),
        reason=_screening_reason(result),
        score=None,
        as_of=as_of,
    )


async def _persist_candidate_rows(
    rows: Sequence[StockUniverseCandidateRow],
    *,
    session_factory: async_sessionmaker[Any] | None,
) -> None:
    owns_engine = session_factory is None
    engine: AsyncEngine | None = None
    active_session_factory = session_factory
    if active_session_factory is None:
        settings = get_settings()
        engine = build_engine(settings)
        active_session_factory = build_session_factory(engine)

    try:
        async with active_session_factory() as session:
            if rows:
                session.add_all(list(rows))
            await session.commit()
    finally:
        if owns_engine and engine is not None:
            await engine.dispose()


def _screening_reason(result: StockScreeningResult) -> str:
    if result.passed:
        return "pass"
    return "; ".join(
        f"{failure.code}: {failure.reason}" for failure in result.failures
    )


def _candidate_source(candidate: StockUniverseCandidate) -> str:
    if not candidate.sources:
        return "unknown"
    return "+".join(source.value for source in candidate.sources)


def _coerce_utc_as_of(as_of: datetime | None) -> datetime:
    if as_of is None:
        return datetime.now(tz=UTC)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        return as_of.replace(tzinfo=UTC)
    return as_of.astimezone(UTC)


def _stub_price(thresholds: StockScreeningThresholds) -> float:
    if thresholds.max_price is None:
        return thresholds.min_price + 25.0
    return (thresholds.min_price + thresholds.max_price) / 2


def _stub_spread_ratio(thresholds: StockScreeningThresholds) -> float:
    spread_limit_ratio = thresholds.max_spread_percent / 100
    if spread_limit_ratio <= 0:
        return 0.0
    return spread_limit_ratio / 2


def _stub_above_threshold(value: float) -> float:
    if value <= 0:
        return 1.0
    return value * 2


__all__ = [
    "STOCK_SCREENER_TASK_NAME",
    "StockScreenerRunResult",
    "StockScreenerStubSnapshot",
    "build_stock_universe_candidate_row",
    "build_stub_stock_screener_snapshot",
    "run_stock_screener",
    "stock_screener_task",
]
