"""Phase S2 stock schema foundation checks."""

from app.db.base import Base
from app.db.models import StockCongressEventRow, StockInsiderEventRow, StockPaperPositionRow


def test_phase_s2_stock_tables_are_registered() -> None:
    """Ensure stock-only schema tables are registered in ORM metadata."""

    expected_tables = {
        "stock_symbols",
        "stock_universe_candidates",
        "stock_watchlist",
        "stock_candles",
        "stock_news_events",
        "stock_congress_events",
        "stock_insider_events",
        "stock_strategy_profiles",
        "stock_paper_positions",
        "stock_paper_fills",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_phase_s2_stock_candles_use_separate_usage_lane() -> None:
    """Stock candles stay separate from crypto candles and preserve usage lanes."""

    table = Base.metadata.tables["stock_candles"]

    for column_name in ("symbol", "timeframe", "timestamp", "source", "usage"):
        assert column_name in table.columns

    assert "asset_class" not in table.columns


def test_phase_s2_stock_context_events_are_not_trade_authorities() -> None:
    """Congress and insider rows remain context/supporting data shells only."""

    assert "direct trigger" in (StockCongressEventRow.__doc__ or "").lower()
    assert "supporting signal" in (StockInsiderEventRow.__doc__ or "").lower()


def test_phase_s2_stock_positions_freeze_max_hold_hours() -> None:
    """Stock positions persist max-hold hours independently at entry."""

    table = Base.metadata.tables["stock_paper_positions"]

    assert "strategy_type" in table.columns
    assert "max_hold_hours" in table.columns
    assert "entry_time" in table.columns
    assert StockPaperPositionRow.__tablename__ == "stock_paper_positions"
