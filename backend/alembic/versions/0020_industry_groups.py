"""Persistent IBD-style industry group classification.

Revision ID: 0020_industry_groups
Revises: 0019_daily_stock_opportunities
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_industry_groups"
down_revision = "0019_daily_stock_opportunities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_groups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("group_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("sector", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_family", sa.String(128), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("taxonomy_version", sa.String(64), nullable=False, server_default="industry_groups_v1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("taxonomy_version", "group_code", name="uq_industry_group_version_code"),
    )
    op.create_index("ix_industry_groups_version_active", "industry_groups", ["taxonomy_version", "active"])

    op.create_table(
        "industry_group_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("industry_pattern", sa.String(255), nullable=False, server_default=""),
        sa.Column("sector_pattern", sa.String(255), nullable=False, server_default=""),
        sa.Column("sic_codes_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sic_description_pattern", sa.String(255), nullable=False, server_default=""),
        sa.Column("target_group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("industry_groups.id"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("source", sa.String(64), nullable=False, server_default="bootstrap"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("taxonomy_version", sa.String(64), nullable=False, server_default="industry_groups_v1"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_industry_group_rules_version_priority", "industry_group_rules", ["taxonomy_version", "active", "priority"])

    op.create_table(
        "industry_group_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("industry_group_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("industry_groups.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="needs_review"),
        sa.Column("classification_source", sa.String(64), nullable=False, server_default=""),
        sa.Column("classification_confidence", sa.Float()),
        sa.Column("classification_fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("sector_snapshot", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_snapshot", sa.String(160), nullable=False, server_default=""),
        sa.Column("sic_snapshot", sa.String(32), nullable=False, server_default=""),
        sa.Column("assignment_version", sa.String(64), nullable=False, server_default="industry_groups_v1"),
        sa.Column("is_manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("override_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("override_at", sa.DateTime(timezone=True)),
        sa.Column("explanation_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("instrument_id", name="uq_industry_group_membership_instrument"),
    )
    op.create_index("ix_industry_group_memberships_status", "industry_group_memberships", ["status"])
    op.create_index("ix_industry_group_memberships_group", "industry_group_memberships", ["industry_group_id"])
    op.create_index("ix_industry_group_memberships_ticker", "industry_group_memberships", ["ticker"])


def downgrade() -> None:
    op.drop_table("industry_group_memberships")
    op.drop_table("industry_group_rules")
    op.drop_table("industry_groups")
