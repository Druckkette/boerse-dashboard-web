"""universe symbol mappings

Revision ID: 0005_universe_symbol_mappings
Revises: 0004_sell_post_mortem_notes
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_universe_symbol_mappings"
down_revision = "0004_sell_post_mortem_notes"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "universe_symbol_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("universe_key", sa.String(96), nullable=False),
        sa.Column("source_ticker", sa.String(32), nullable=False),
        sa.Column("yahoo_symbol", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("universe_key", "source_ticker", name="uq_universe_symbol_mapping"),
    )
    op.create_index("ix_universe_symbol_mappings_universe_key", "universe_symbol_mappings", ["universe_key"])
    op.create_index("ix_universe_symbol_mappings_source_ticker", "universe_symbol_mappings", ["source_ticker"])
    op.create_index("ix_universe_symbol_mappings_yahoo_symbol", "universe_symbol_mappings", ["yahoo_symbol"])
    op.create_index("ix_universe_symbol_mappings_status", "universe_symbol_mappings", ["status"])
    op.create_index(
        "ix_universe_symbol_mappings_universe_status",
        "universe_symbol_mappings",
        ["universe_key", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_universe_symbol_mappings_universe_status", table_name="universe_symbol_mappings")
    op.drop_index("ix_universe_symbol_mappings_status", table_name="universe_symbol_mappings")
    op.drop_index("ix_universe_symbol_mappings_yahoo_symbol", table_name="universe_symbol_mappings")
    op.drop_index("ix_universe_symbol_mappings_source_ticker", table_name="universe_symbol_mappings")
    op.drop_index("ix_universe_symbol_mappings_universe_key", table_name="universe_symbol_mappings")
    op.drop_table("universe_symbol_mappings")
