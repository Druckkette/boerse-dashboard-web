"""Keep portfolio quote observations and issuer evidence after products disappear."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024_portfolio_price_archive"
down_revision = "0023_price_split_factor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("portfolio_price_archive",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("instrument_key", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("payload_gzip", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("instrument_key", "kind", "sha256", name="uq_portfolio_price_archive"))
    op.create_index("ix_portfolio_archive_key_date", "portfolio_price_archive", ["instrument_key", "price_date"])


def downgrade() -> None:
    op.drop_table("portfolio_price_archive")
