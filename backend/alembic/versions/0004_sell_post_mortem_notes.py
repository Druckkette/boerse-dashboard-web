"""sell post mortem notes

Revision ID: 0004_sell_post_mortem_notes
Revises: 0003_fundamental_snapshots
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_sell_post_mortem_notes"
down_revision = "0003_fundamental_snapshots"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "sell_post_mortem_notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("check_key", sa.String(96), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("ticker", "check_key", name="uq_sell_post_mortem_ticker_check"),
    )
    op.create_index("ix_sell_post_mortem_notes_ticker", "sell_post_mortem_notes", ["ticker"])
    op.create_index("ix_sell_post_mortem_notes_check_key", "sell_post_mortem_notes", ["check_key"])
    op.create_index("ix_sell_post_mortem_notes_status", "sell_post_mortem_notes", ["status"])
    op.create_index(
        "ix_sell_post_mortem_ticker_status",
        "sell_post_mortem_notes",
        ["ticker", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_sell_post_mortem_ticker_status", table_name="sell_post_mortem_notes")
    op.drop_index("ix_sell_post_mortem_notes_status", table_name="sell_post_mortem_notes")
    op.drop_index("ix_sell_post_mortem_notes_check_key", table_name="sell_post_mortem_notes")
    op.drop_index("ix_sell_post_mortem_notes_ticker", table_name="sell_post_mortem_notes")
    op.drop_table("sell_post_mortem_notes")
