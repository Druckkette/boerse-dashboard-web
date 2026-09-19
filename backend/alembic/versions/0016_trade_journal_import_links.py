"""Link broker executions, position cycles and journal entries without rewriting history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_trade_journal_import_links"
down_revision = "0015_refresh_work_items"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trade_journal_entries", sa.Column("source_transaction_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("transactions.id"), nullable=True))
    op.create_unique_constraint("uq_journal_source_transaction", "trade_journal_entries", ["source_transaction_id"])
    op.add_column("trade_journal_entries", sa.Column("trade_group_id", sa.String(64), nullable=True))
    op.create_index("ix_journal_trade_group", "trade_journal_entries", ["trade_group_id"])
    op.add_column("trade_journal_entries", sa.Column("position_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("positions.id"), nullable=True))
    op.add_column("trade_journal_entries", sa.Column("currency", sa.String(8), server_default="USD", nullable=False))
    op.add_column("trade_journal_entries", sa.Column("realized_pnl", sa.Float(), nullable=True))
    op.add_column("trade_journal_entries", sa.Column("sell_assessment_json", postgresql.JSONB(), server_default="{}", nullable=False))
    op.add_column("positions", sa.Column("import_trade_key", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_position_import_trade_key", "positions", ["import_trade_key"])


def downgrade():
    op.drop_constraint("uq_position_import_trade_key", "positions", type_="unique")
    op.drop_column("positions", "import_trade_key")
    op.drop_constraint("uq_journal_source_transaction", "trade_journal_entries", type_="unique")
    op.drop_index("ix_journal_trade_group", table_name="trade_journal_entries")
    for name in ("source_transaction_id", "trade_group_id", "position_id", "currency", "realized_pnl", "sell_assessment_json"):
        op.drop_column("trade_journal_entries", name)
