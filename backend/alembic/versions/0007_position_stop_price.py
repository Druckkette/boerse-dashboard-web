"""position stop price override

Revision ID: 0007_position_stop_price
Revises: 0006_sell_ranking_snapshots
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_position_stop_price"
down_revision = "0006_sell_ranking_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("stop_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "stop_price")
