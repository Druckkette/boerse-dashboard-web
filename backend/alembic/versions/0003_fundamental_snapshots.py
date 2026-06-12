"""fundamental snapshots

Revision ID: 0003_fundamental_snapshots
Revises: 0002_worker_nas_schema
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_fundamental_snapshots"
down_revision = "0002_worker_nas_schema"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "fundamental_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("fiscal_period", sa.String(32), nullable=False),
        sa.Column("quarterly_eps_growth_pct", sa.Float(), nullable=True),
        sa.Column("annual_eps_growth_pct", sa.Float(), nullable=True),
        sa.Column("quarterly_revenue_growth_pct", sa.Float(), nullable=True),
        sa.Column("annual_revenue_growth_pct", sa.Float(), nullable=True),
        sa.Column("roe_pct", sa.Float(), nullable=True),
        sa.Column("profit_margin_pct", sa.Float(), nullable=True),
        sa.Column("trailing_eps", sa.Float(), nullable=True),
        sa.Column("quarterly_eps_accelerating", sa.Boolean(), nullable=True),
        sa.Column("quarterly_revenue_accelerating", sa.Boolean(), nullable=True),
        sa.Column("institutional_holders", sa.Integer(), nullable=True),
        sa.Column("institutional_ownership_pct", sa.Float(), nullable=True),
        sa.Column("next_earnings_date", sa.Date(), nullable=True),
        sa.Column("beta", sa.Float(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("instrument_id", "as_of", "source", name="uq_fundamental_snapshot"),
    )
    op.create_index("ix_fundamental_snapshots_instrument_id", "fundamental_snapshots", ["instrument_id"])
    op.create_index("ix_fundamental_snapshots_ticker", "fundamental_snapshots", ["ticker"])
    op.create_index("ix_fundamental_snapshots_as_of", "fundamental_snapshots", ["as_of"])
    op.create_index(
        "ix_fundamental_snapshots_ticker_as_of",
        "fundamental_snapshots",
        ["ticker", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_fundamental_snapshots_ticker_as_of", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_as_of", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_ticker", table_name="fundamental_snapshots")
    op.drop_index("ix_fundamental_snapshots_instrument_id", table_name="fundamental_snapshots")
    op.drop_table("fundamental_snapshots")
