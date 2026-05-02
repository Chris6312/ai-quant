"""Phase S5 stock screener worker tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

import pytest

from app.db.stock_models import StockUniverseCandidateRow
from app.stock.universe import StockUniverseCandidate
from app.stock.validation import StockScreeningFailure, StockScreeningResult
from app.tasks import stock_screener


class _FakeSession:
    """Capture ORM rows written by the worker."""

    def __init__(self) -> None:
        self.rows: list[StockUniverseCandidateRow] = []
        self.commit_count = 0

    def add_all(self, rows: Sequence[StockUniverseCandidateRow]) -> None:
        self.rows.extend(rows)

    async def commit(self) -> None:
        self.commit_count += 1


class _FakeSessionContext:
    """Async context manager returned by the fake session factory."""

    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> _FakeSession:
        return self.session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exc_type, exc, traceback


class _FakeSessionFactory:
    """Callable test double shaped like async_sessionmaker."""

    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self) -> _FakeSessionContext:
        return _FakeSessionContext(self.session)


@pytest.mark.asyncio
async def test_run_stock_screener_processes_candidates_and_persists_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Universe candidates should be screened and persisted as pass rows."""

    calls: list[str] = []

    def _screen_pass(**kwargs: object) -> StockScreeningResult:
        candidate = cast(StockUniverseCandidate, kwargs["candidate"])
        calls.append(candidate.symbol)
        return StockScreeningResult(symbol=candidate.symbol, passed=True)

    monkeypatch.setattr(stock_screener, "screen_stock_candidate", _screen_pass)
    session = _FakeSession()
    as_of = datetime(2026, 5, 1, 15, 30)

    result = await stock_screener.run_stock_screener(
        manual=[" aapl ", "MSFT"],
        as_of=as_of,
        session_factory=cast(object, _FakeSessionFactory(session)),
    )

    assert calls == ["AAPL", "MSFT"]
    assert result.as_of == datetime(2026, 5, 1, 15, 30, tzinfo=UTC)
    assert result.candidate_count == 2
    assert result.passed_count == 2
    assert result.failed_count == 0
    assert result.persisted_count == 2
    assert session.commit_count == 1
    assert [row.symbol for row in session.rows] == ["AAPL", "MSFT"]
    assert {row.reason for row in session.rows} == {"pass"}
    assert {row.score for row in session.rows} == {None}
    assert {row.source for row in session.rows} == {"manual"}
    assert all(row.as_of == result.as_of for row in session.rows)
    assert all(row.id for row in session.rows)


@pytest.mark.asyncio
async def test_run_stock_screener_persists_failure_reason_from_screening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure rows should keep compact failure reason text."""

    def _screen_mixed(**kwargs: object) -> StockScreeningResult:
        candidate = cast(StockUniverseCandidate, kwargs["candidate"])
        if candidate.symbol == "AAPL":
            return StockScreeningResult(symbol=candidate.symbol, passed=True)
        return StockScreeningResult(
            symbol=candidate.symbol,
            passed=False,
            failures=(
                StockScreeningFailure(
                    code="stub_failure",
                    reason="local stub rejected candidate",
                ),
            ),
        )

    monkeypatch.setattr(stock_screener, "screen_stock_candidate", _screen_mixed)
    session = _FakeSession()

    result = await stock_screener.run_stock_screener(
        manual=["AAPL", "MSFT"],
        as_of=datetime(2026, 5, 1, tzinfo=UTC),
        session_factory=cast(object, _FakeSessionFactory(session)),
    )

    reason_by_symbol = {row.symbol: row.reason for row in session.rows}
    assert result.passed_count == 1
    assert result.failed_count == 1
    assert reason_by_symbol["AAPL"] == "pass"
    assert reason_by_symbol["MSFT"] == (
        "stub_failure: local stub rejected candidate"
    )


@pytest.mark.asyncio
async def test_run_stock_screener_unsupported_candidates_do_not_crash() -> None:
    """Unsupported symbols should persist failed rows instead of stopping the run."""

    session = _FakeSession()

    result = await stock_screener.run_stock_screener(
        manual=["BRK.B", "BTC/USD", " "],
        as_of=datetime(2026, 5, 1, tzinfo=UTC),
        session_factory=cast(object, _FakeSessionFactory(session)),
    )

    reason_by_symbol = {row.symbol: row.reason or "" for row in session.rows}
    assert result.candidate_count == 3
    assert result.passed_count == 0
    assert result.failed_count == 3
    assert "contains unsupported provider character" in reason_by_symbol["BRK.B"]
    assert "contains unsupported provider character" in reason_by_symbol["BTC/USD"]
    assert "symbol is empty" in reason_by_symbol[""]


def test_stock_screener_does_not_import_provider_fetch_clients() -> None:
    """S5 should not introduce provider fetching surfaces."""

    forbidden_client_names = {
        "AlpacaTrainingFetcher",
        "KrakenRestCandleClient",
        "StockHistoricalCandleProvider",
        "StockIntradayCandleProvider",
        "StockQuoteProvider",
    }

    assert not any(
        hasattr(stock_screener, client_name)
        for client_name in forbidden_client_names
    )
