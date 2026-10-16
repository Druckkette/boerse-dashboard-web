"""Keep the exact split adjustment of each downloaded price snapshot."""
from alembic import op
import sqlalchemy as sa

revision = "0023_price_split_factor"
down_revision = "0022_trade_journal_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_bars", sa.Column("split_adjustment_factor", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("price_bars", "split_adjustment_factor")
