"""Track actual price fetch time without inventing timestamps for old bars."""
from alembic import op
import sqlalchemy as sa

revision = "0014_price_fetch_time"
down_revision = "0013_stock_assessment_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("price_bars", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
    # Derived recommendations may contain the former EUR/USD mismatch.
    op.execute("DELETE FROM sell_ranking_snapshots")


def downgrade():
    op.drop_column("price_bars", "fetched_at")
