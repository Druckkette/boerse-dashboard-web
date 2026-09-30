"""Versioned historical context and journal note revisions.

Revision ID: 0022_trade_journal_history
Revises: 0021_industry_group_rs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_trade_journal_history"
down_revision = "0021_industry_group_rs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_assessment_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("instruments.id")),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("information_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_as_of", sa.Date()),
        sa.Column("status", sa.String(32), nullable=False, server_default="archived"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assessment_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("ruleset_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("data_fingerprint", sa.String(128), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="daily_archive"),
        sa.Column("coverage_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("ticker", "session_date", "data_fingerprint", name="uq_stock_assessment_history_version"),
    )
    op.create_index("ix_stock_assessment_history_ticker", "stock_assessment_history", ["ticker"])
    op.create_index("ix_stock_assessment_history_session_date", "stock_assessment_history", ["session_date"])
    op.create_index("ix_stock_assessment_history_lookup", "stock_assessment_history", ["ticker", "information_cutoff"])

    op.create_table(
        "market_assessment_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("benchmark", sa.String(32), nullable=False, server_default="SPY"),
        sa.Column("universe", sa.String(96), nullable=False, server_default="us_common_stocks"),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("information_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="archived"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assessment_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("ruleset_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("data_fingerprint", sa.String(128), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="daily_archive"),
        sa.Column("coverage_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("benchmark", "session_date", "data_fingerprint", name="uq_market_assessment_history_version"),
    )
    op.create_index("ix_market_assessment_history_benchmark", "market_assessment_history", ["benchmark"])
    op.create_index("ix_market_assessment_history_session_date", "market_assessment_history", ["session_date"])
    op.create_index("ix_market_assessment_history_lookup", "market_assessment_history", ["benchmark", "information_cutoff"])

    op.create_table(
        "journal_context_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trade_journal_entries.id"), nullable=False),
        sa.Column("block_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("origin", sa.String(64), nullable=False, server_default="reconstruction"),
        sa.Column("information_cutoff", sa.DateTime(timezone=True)),
        sa.Column("data_as_of", sa.Date()),
        sa.Column("archive_reference_id", sa.String(64)),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assessment_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("ruleset_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("data_fingerprint", sa.String(128), nullable=False),
        sa.Column("sources_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reason_codes_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("journal_entry_id", "block_type", "data_fingerprint", name="uq_journal_context_version"),
    )
    op.create_index("ix_journal_context_versions_journal_entry_id", "journal_context_versions", ["journal_entry_id"])
    op.create_index("ix_journal_context_versions_block_type", "journal_context_versions", ["block_type"])
    op.create_index("ix_journal_context_versions_status", "journal_context_versions", ["status"])
    op.create_index("ix_journal_context_entry_block", "journal_context_versions", ["journal_entry_id", "block_type", "generated_at"])

    op.create_table(
        "trade_journal_note_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trade_journal_entries.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("journal_entry_id", "revision", name="uq_trade_journal_note_revision"),
    )
    op.create_index("ix_trade_journal_note_revisions_journal_entry_id", "trade_journal_note_revisions", ["journal_entry_id"])
    op.create_index("ix_trade_journal_note_entry_created", "trade_journal_note_revisions", ["journal_entry_id", "created_at"])


def downgrade() -> None:
    op.drop_table("trade_journal_note_revisions")
    op.drop_table("journal_context_versions")
    op.drop_table("market_assessment_history")
    op.drop_table("stock_assessment_history")

