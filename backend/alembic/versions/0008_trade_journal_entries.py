"""trade journal entries

Revision ID: 0008_trade_journal_entries
Revises: 0007_position_stop_price
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_trade_journal_entries"
down_revision = "0007_position_stop_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("stop_distance_pct", sa.Float(), nullable=True),
        sa.Column("linked_entry_id", sa.String(length=64), nullable=True),
        sa.Column("realized_pnl_eur", sa.Float(), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("stop_deviation_pct", sa.Float(), nullable=True),
        sa.Column("basis_text", sa.Text(), nullable=False),
        sa.Column("alternative_entry", sa.Boolean(), nullable=False),
        sa.Column("primary_reasons", sa.Text(), nullable=False),
        sa.Column("sell_reason", sa.Text(), nullable=False),
        sa.Column("questionnaire_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stock_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("market_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("portfolio_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chart_images_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trade_journal_entries_ticker"), "trade_journal_entries", ["ticker"], unique=False)
    op.create_index(
        "ix_trade_journal_ticker_type_status",
        "trade_journal_entries",
        ["ticker", "entry_type", "status"],
        unique=False,
    )
    op.create_index("ix_trade_journal_trade_date", "trade_journal_entries", ["trade_date"], unique=False)
    op.create_index("ix_trade_journal_linked_entry", "trade_journal_entries", ["linked_entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trade_journal_linked_entry", table_name="trade_journal_entries")
    op.drop_index("ix_trade_journal_trade_date", table_name="trade_journal_entries")
    op.drop_index("ix_trade_journal_ticker_type_status", table_name="trade_journal_entries")
    op.drop_index(op.f("ix_trade_journal_entries_ticker"), table_name="trade_journal_entries")
    op.drop_table("trade_journal_entries")
