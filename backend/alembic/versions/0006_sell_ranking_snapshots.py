"""sell ranking snapshots

Revision ID: 0006_sell_ranking_snapshots
Revises: 0005_universe_symbol_mappings
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_sell_ranking_snapshots"
down_revision = "0005_universe_symbol_mappings"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "sell_ranking_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pending_status", sa.String(32), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recommendation_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("source_job_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("item_json", JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("ticker", name="uq_sell_ranking_snapshot_ticker"),
    )
    op.create_index("ix_sell_ranking_snapshots_ticker", "sell_ranking_snapshots", ["ticker"])
    op.create_index("ix_sell_ranking_snapshots_status", "sell_ranking_snapshots", ["status"])
    op.create_index("ix_sell_ranking_snapshots_pending_status", "sell_ranking_snapshots", ["pending_status"])
    op.create_index("ix_sell_ranking_snapshots_source_job_id", "sell_ranking_snapshots", ["source_job_id"])
    op.create_index(
        "ix_sell_ranking_snapshots_status_recommendation",
        "sell_ranking_snapshots",
        ["status", "recommendation_pct"],
    )
    op.create_index(
        "ix_sell_ranking_snapshots_generated_at",
        "sell_ranking_snapshots",
        ["generated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sell_ranking_snapshots_generated_at", table_name="sell_ranking_snapshots")
    op.drop_index("ix_sell_ranking_snapshots_status_recommendation", table_name="sell_ranking_snapshots")
    op.drop_index("ix_sell_ranking_snapshots_source_job_id", table_name="sell_ranking_snapshots")
    op.drop_index("ix_sell_ranking_snapshots_pending_status", table_name="sell_ranking_snapshots")
    op.drop_index("ix_sell_ranking_snapshots_status", table_name="sell_ranking_snapshots")
    op.drop_index("ix_sell_ranking_snapshots_ticker", table_name="sell_ranking_snapshots")
    op.drop_table("sell_ranking_snapshots")
