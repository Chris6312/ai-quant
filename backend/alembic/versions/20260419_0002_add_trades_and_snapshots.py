"""Add trades and portfolio snapshots tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260419_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create trade and portfolio snapshot tables."""

    op.create_table(
        "trades",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "position_id",
            sa.String(length=36),
            sa.ForeignKey("positions.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(), nullable=False),
        sa.Column("exit_price", sa.Numeric(), nullable=False),
        sa.Column("size", sa.Numeric(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False),
        sa.Column(
            "commission",
            sa.Numeric(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_trades_symbol_closed_at",
        "trades",
        [sa.column("symbol"), sa.column("closed_at").desc()],
        unique=False,
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nav", sa.Numeric(), nullable=False),
        sa.Column("stock_cash", sa.Numeric(), nullable=False),
        sa.Column("crypto_cash", sa.Numeric(), nullable=False),
        sa.Column("open_position_count", sa.Integer(), nullable=False),
        sa.Column("realized_pnl_today", sa.Numeric(), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_portfolio_snapshots_snapshot_at",
        "portfolio_snapshots",
        [sa.column("snapshot_at").desc()],
        unique=False,
    )


def downgrade() -> None:
    """Drop trade and portfolio snapshot tables."""

    op.drop_index(
        "ix_portfolio_snapshots_snapshot_at",
        table_name="portfolio_snapshots",
    )
    op.drop_table("portfolio_snapshots")
    op.drop_index(
        "ix_trades_symbol_closed_at",
        table_name="trades",
    )
    op.drop_table("trades")
