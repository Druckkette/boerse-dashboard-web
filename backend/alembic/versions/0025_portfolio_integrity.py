"""Preserve quote units and reject repeated or nonfinite manual bookings."""
from alembic import op
import sqlalchemy as sa

revision = "0025_portfolio_integrity"
down_revision = "0024_portfolio_price_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_bars", sa.Column("quote_currency", sa.String(8), nullable=True))
    op.add_column("transactions", sa.Column("booking_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_transactions_booking_id", "transactions", ["booking_id"])
    # Do not rewrite old financial records. NOT VALID still enforces every new
    # write while allowing existing anomalies to be inspected separately.
    for table, fields in {
        "transactions": ("shares", "price", "fees", "tax", "gross_amount", "net_amount"),
        "positions": ("shares", "buy_price", "stop_price", "stop_pct"),
        "cash_flows": ("amount",),
    }.items():
        condition = " AND ".join(f"({field} > '-Infinity'::float8 AND {field} < 'Infinity'::float8)" for field in fields)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_finite CHECK ({condition}) NOT VALID")


def downgrade() -> None:
    for table in ("transactions", "positions", "cash_flows"):
        op.drop_constraint(f"ck_{table}_finite", table, type_="check")
    op.drop_constraint("uq_transactions_booking_id", "transactions", type_="unique")
    op.drop_column("transactions", "booking_id")
    op.drop_column("price_bars", "quote_currency")
