"""add stock assessment snapshots

Revision ID: 0013_stock_assessment_snapshots
Revises: 0012_freshness_indexes
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_stock_assessment_snapshots"
down_revision = "0012_freshness_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=False)
    op.create_table(
        "stock_assessment_snapshots",
        sa.Column("id", uuid, nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("technical_score", sa.Float(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_job_id", sa.String(length=96), nullable=False),
        sa.Column("item_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", name="uq_stock_assessment_snapshot_ticker"),
    )
    op.create_index("ix_stock_assessment_snapshots_ticker", "stock_assessment_snapshots", ["ticker"])
    op.create_index("ix_stock_assessment_snapshots_as_of", "stock_assessment_snapshots", ["as_of"])
    op.create_index(
        "ix_stock_assessment_snapshots_score",
        "stock_assessment_snapshots",
        ["overall_score", "technical_score"],
    )
    op.create_index(
        "ix_stock_assessment_snapshots_generated_at",
        "stock_assessment_snapshots",
        ["generated_at"],
    )
    op.create_index(
        "ix_stock_assessment_snapshots_source_job_id",
        "stock_assessment_snapshots",
        ["source_job_id"],
    )


def downgrade() -> None:
    op.drop_table("stock_assessment_snapshots")
