"""Durable, resumable report work, independent of Redis delivery."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_refresh_work_items"
down_revision = "0014_price_fetch_time"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refresh_work_items",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("data_group", sa.String(32), nullable=False),
        sa.Column("revision", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_work_due", "refresh_work_items", ["status", "due_at"])
    op.create_index("ix_refresh_work_items_ticker", "refresh_work_items", ["ticker"])


def downgrade():
    op.drop_table("refresh_work_items")
