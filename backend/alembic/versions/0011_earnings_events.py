"""add earnings event calendar

Revision ID: 0011_earnings_events
Revises: 0010_job_heartbeat
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_earnings_events"
down_revision = "0010_job_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "earnings_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("fiscal_date_ending", sa.Date(), nullable=True),
        sa.Column("time", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("eps_estimated", sa.Float(), nullable=True),
        sa.Column("eps_actual", sa.Float(), nullable=True),
        sa.Column("revenue_estimated", sa.Float(), nullable=True),
        sa.Column("revenue_actual", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="fmp"),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "event_date", "source", name="uq_earnings_event"),
    )
    op.create_index("ix_earnings_events_ticker", "earnings_events", ["ticker"], unique=False)
    op.create_index("ix_earnings_events_event_date", "earnings_events", ["event_date"], unique=False)
    op.create_index("ix_earnings_events_date_ticker", "earnings_events", ["event_date", "ticker"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_earnings_events_date_ticker", table_name="earnings_events")
    op.drop_index("ix_earnings_events_event_date", table_name="earnings_events")
    op.drop_index("ix_earnings_events_ticker", table_name="earnings_events")
    op.drop_table("earnings_events")
