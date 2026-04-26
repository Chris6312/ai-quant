"""Phase 10 durable paper ledger schema checks."""

from app.db.base import Base


def test_phase10_paper_ledger_tables_are_registered() -> None:
    """Ensure ORM metadata contains the durable paper ledger tables."""

    expected_tables = {
        "paper_account",
        "paper_positions",
        "paper_orders",
        "paper_fills",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_phase10_paper_account_tracks_cash_and_resets() -> None:
    """Ensure paper account records can survive reset and restart workflows."""

    table = Base.metadata.tables["paper_account"]

    for column_name in (
        "asset_class",
        "cash_balance",
        "default_cash_balance",
        "realized_pnl",
        "reset_count",
        "last_reset_at",
    ):
        assert column_name in table.columns


def test_phase10_paper_fill_links_order_and_position() -> None:
    """Ensure fill records are the immutable audit trail for paper execution."""

    table = Base.metadata.tables["paper_fills"]

    assert "order_id" in table.columns
    assert "position_id" in table.columns
    assert "cash_after" in table.columns
    assert "realized_pnl" in table.columns
