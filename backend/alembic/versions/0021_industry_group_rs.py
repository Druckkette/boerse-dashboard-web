"""Industry Group relative-strength snapshots.

Revision ID: 0021_industry_group_rs
Revises: 0020_industry_groups
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_industry_group_rs"
down_revision = "0020_industry_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_group_rs_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("industry_group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("industry_groups.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False, server_default="industry_groups_v4"),
        sa.Column("algorithm_version", sa.String(64), nullable=False, server_default="industry_group_rs_v1"),
        sa.Column("benchmark_ticker", sa.String(32), nullable=False, server_default="SPY"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issuer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("return_1d", sa.Float()),
        sa.Column("return_1m", sa.Float()),
        sa.Column("return_3m", sa.Float()),
        sa.Column("return_6m", sa.Float()),
        sa.Column("return_12m", sa.Float()),
        sa.Column("benchmark_return_1d", sa.Float()),
        sa.Column("benchmark_return_1m", sa.Float()),
        sa.Column("benchmark_return_3m", sa.Float()),
        sa.Column("benchmark_return_6m", sa.Float()),
        sa.Column("benchmark_return_12m", sa.Float()),
        sa.Column("excess_return_1m", sa.Float()),
        sa.Column("excess_return_3m", sa.Float()),
        sa.Column("excess_return_6m", sa.Float()),
        sa.Column("excess_return_12m", sa.Float()),
        sa.Column("rs_1m", sa.Float()),
        sa.Column("rs_3m", sa.Float()),
        sa.Column("rs_6m", sa.Float()),
        sa.Column("rs_12m", sa.Float()),
        sa.Column("rs_score", sa.Float()),
        sa.Column("rank", sa.Integer()),
        sa.Column("ranked_group_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_ranked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("member_metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("performance_series_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "industry_group_id",
            "snapshot_date",
            "algorithm_version",
            name="uq_industry_group_rs_group_date_algo",
        ),
    )
    op.create_index(
        "ix_industry_group_rs_date_rank",
        "industry_group_rs_snapshots",
        ["snapshot_date", "is_ranked", "rank"],
    )
    op.create_index(
        "ix_industry_group_rs_group_date",
        "industry_group_rs_snapshots",
        ["industry_group_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_table("industry_group_rs_snapshots")
