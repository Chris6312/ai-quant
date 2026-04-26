"""Add durable paper trading ledger tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260426_0007"
down_revision = "20260424_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable paper ledger tables."""

    op.create_table(
        "paper_account",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("cash_balance", sa.Numeric(), nullable=False),
        sa.Column("default_cash_balance", sa.Numeric(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("reset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_class", name="uq_paper_account_asset_class"),
    )
    op.create_table(
        "paper_positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("size", sa.Numeric(), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_positions_symbol_status",
        "paper_positions",
        ["symbol", "status"],
    )
    op.create_index(
        "ix_paper_positions_asset_status",
        "paper_positions",
        ["asset_class", "status"],
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("requested_size", sa.Numeric(), nullable=False),
        sa.Column("limit_price", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("filled_size", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("average_fill_price", sa.Numeric(), nullable=True),
        sa.Column("remaining_size", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="paper"),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_orders_symbol_created",
        "paper_orders",
        ["symbol", "created_at"],
    )
    op.create_index(
        "ix_paper_orders_status_created",
        "paper_orders",
        ["status", "created_at"],
    )
    op.create_table(
        "paper_fills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("fill_size", sa.Numeric(), nullable=False),
        sa.Column("fill_price", sa.Numeric(), nullable=False),
        sa.Column("gross", sa.Numeric(), nullable=False),
        sa.Column("commission", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("cash_after", sa.Numeric(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="paper"),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["paper_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["paper_positions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_fills_order", "paper_fills", ["order_id"])
    op.create_index(
        "ix_paper_fills_symbol_filled",
        "paper_fills",
        ["symbol", "filled_at"],
    )


def downgrade() -> None:
    """Drop durable paper ledger tables."""

    op.drop_index("ix_paper_fills_symbol_filled", table_name="paper_fills")
    op.drop_index("ix_paper_fills_order", table_name="paper_fills")
    op.drop_table("paper_fills")
    op.drop_index("ix_paper_orders_status_created", table_name="paper_orders")
    op.drop_index("ix_paper_orders_symbol_created", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_index("ix_paper_positions_asset_status", table_name="paper_positions")
    op.drop_index("ix_paper_positions_symbol_status", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_table("paper_account")
