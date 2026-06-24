"""trade journal alternative entry text

Revision ID: 0009_trade_journal_alt_text
Revises: 0008_trade_journal_entries
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_trade_journal_alt_text"
down_revision = "0008_trade_journal_entries"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("trade_journal_entries", "alternative_entry_text"):
        op.add_column(
            "trade_journal_entries",
            sa.Column("alternative_entry_text", sa.Text(), nullable=False, server_default=""),
        )
    op.alter_column("trade_journal_entries", "alternative_entry_text", server_default=None)


def downgrade() -> None:
    if not _column_exists("trade_journal_entries", "alternative_entry_text"):
        return
    op.drop_column("trade_journal_entries", "alternative_entry_text")
