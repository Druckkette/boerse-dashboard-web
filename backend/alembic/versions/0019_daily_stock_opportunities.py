"""Compact daily score and opportunity history.

Revision ID: 0019_daily_stock_opportunities
Revises: 0018_nonperiod_filing_checks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019_daily_stock_opportunities"
down_revision = "0018_nonperiod_filing_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_stock_opportunities",
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("technical_score", sa.Float(), nullable=False),
        sa.Column("fundamental_score", sa.Float(), nullable=False),
        sa.Column("moving_average_score", sa.Float(), nullable=False),
        sa.Column("chart_behavior_score", sa.Integer(), nullable=False),
        sa.Column("rs_rating", sa.Integer()),
        sa.Column("signals_json", postgresql.JSONB(), nullable=False),
        sa.Column("daily_dynamics_score", sa.Float()),
        sa.Column("daily_opportunity_score", sa.Float()),
        sa.Column("rank", sa.Integer()),
        sa.Column("details_json", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("as_of", "ticker"),
    )
    op.create_index("ix_daily_stock_opportunities_day_rank", "daily_stock_opportunities", ["as_of", "rank"])


def downgrade() -> None:
    op.drop_index("ix_daily_stock_opportunities_day_rank", table_name="daily_stock_opportunities")
    op.drop_table("daily_stock_opportunities")
