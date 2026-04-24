"""Add persisted ML prediction and SHAP tables."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260424_0005"
down_revision = "20260422_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create prediction persistence tables."""

    op.create_table(
        "predictions",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=96), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("probability_down", sa.Float(), nullable=False),
        sa.Column("probability_flat", sa.Float(), nullable=False),
        sa.Column("probability_up", sa.Float(), nullable=False),
        sa.Column("confidence_threshold", sa.Float(), nullable=False),
        sa.Column("gate_outcome", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("top_driver", sa.String(length=128), nullable=True),
        sa.Column("candle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column(
            "signal_event_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("signal_event", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_predictions_asset_created", "predictions", ["asset_class", "created_at"])
    op.create_index("ix_predictions_symbol_candle", "predictions", ["symbol", "candle_time"])
    op.create_table(
        "prediction_shap",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("prediction_id", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=False),
        sa.Column("feature_value", sa.Float(), nullable=False),
        sa.Column("shap_value", sa.Float(), nullable=False),
        sa.Column("abs_value", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prediction_shap_prediction_abs",
        "prediction_shap",
        ["prediction_id", "abs_value"],
    )


def downgrade() -> None:
    """Drop prediction persistence tables."""

    op.drop_index("ix_prediction_shap_prediction_abs", table_name="prediction_shap")
    op.drop_table("prediction_shap")
    op.drop_index("ix_predictions_symbol_candle", table_name="predictions")
    op.drop_index("ix_predictions_asset_created", table_name="predictions")
    op.drop_table("predictions")
