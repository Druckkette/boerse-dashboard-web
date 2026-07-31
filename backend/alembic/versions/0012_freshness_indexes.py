"""add freshness query indexes

Revision ID: 0012_freshness_indexes
Revises: 0011_earnings_events
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_freshness_indexes"
down_revision = "0011_earnings_events"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _index_exists("rs_ratings", "ix_rs_ratings_source_date"):
        op.create_index(
            "ix_rs_ratings_source_date",
            "rs_ratings",
            ["source", "date"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists("rs_ratings", "ix_rs_ratings_source_date"):
        op.drop_index("ix_rs_ratings_source_date", table_name="rs_ratings")
