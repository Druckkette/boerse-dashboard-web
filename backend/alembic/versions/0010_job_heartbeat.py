"""add worker heartbeat to jobs

Revision ID: 0010_job_heartbeat
Revises: 0009_trade_journal_alt_text
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_job_heartbeat"
down_revision = "0009_trade_journal_alt_text"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _column_exists("jobs", "heartbeat_at"):
        op.add_column(
            "jobs",
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    if not _index_exists("jobs", "ix_jobs_status_heartbeat_at"):
        op.create_index("ix_jobs_status_heartbeat_at", "jobs", ["status", "heartbeat_at"], unique=False)


def downgrade() -> None:
    if _index_exists("jobs", "ix_jobs_status_heartbeat_at"):
        op.drop_index("ix_jobs_status_heartbeat_at", table_name="jobs")
    if _column_exists("jobs", "heartbeat_at"):
        op.drop_column("jobs", "heartbeat_at")
