"""worker and NAS schema

Revision ID: 0002_worker_nas_schema
Revises: 0001_initial_skeleton
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_worker_nas_schema"
down_revision = "0001_initial_skeleton"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("instruments", sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"))
    op.add_column("instruments", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")))
    op.add_column("price_bars", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")))
    op.create_index("ix_price_bars_instrument_date", "price_bars", ["instrument_id", "date"])

    op.create_table(
        "universes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_universes_key", "universes", ["key"])
    op.create_index("ix_universes_is_active", "universes", ["is_active"])

    op.create_table(
        "universe_members",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("universe_id", UUID, sa.ForeignKey("universes.id"), nullable=False),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("universe_id", "instrument_id", "valid_from", name="uq_universe_member"),
    )
    op.create_index("ix_universe_members_universe_id", "universe_members", ["universe_id"])
    op.create_index("ix_universe_members_instrument_id", "universe_members", ["instrument_id"])
    op.create_index("ix_universe_members_ticker", "universe_members", ["ticker"])
    op.create_index(
        "ix_universe_members_universe_instrument",
        "universe_members",
        ["universe_id", "instrument_id"],
    )

    op.add_column("breadth_daily", sa.Column("pct_above_20sma", sa.Float(), nullable=True))
    op.add_column("breadth_daily", sa.Column("new_highs", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("breadth_daily", sa.Column("new_lows", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("breadth_daily", sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"))

    op.add_column("rs_ratings", sa.Column("percentile", sa.Float(), nullable=True))
    op.add_column("rs_ratings", sa.Column("metadata_json", JSONB, nullable=False, server_default="{}"))
    op.create_index("ix_rs_ratings_instrument_date", "rs_ratings", ["instrument_id", "date"])

    op.add_column("positions", sa.Column("broker", sa.String(64), nullable=False, server_default=""))
    op.add_column("positions", sa.Column("account", sa.String(64), nullable=False, server_default=""))
    op.add_column("positions", sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()")))
    op.add_column("positions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "imports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_imports_source", "imports", ["source"])
    op.create_index("ix_imports_status", "imports", ["status"])

    op.create_table(
        "transactions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("position_id", UUID, sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("tax", sa.Float(), nullable=False),
        sa.Column("gross_amount", sa.Float(), nullable=True),
        sa.Column("net_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("broker", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("import_id", UUID, sa.ForeignKey("imports.id"), nullable=True),
        sa.Column("raw_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_transactions_ticker", "transactions", ["ticker"])
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_transaction_type", "transactions", ["transaction_type"])
    op.create_index("ix_transactions_external_id", "transactions", ["external_id"])
    op.create_index("ix_transactions_ticker_date", "transactions", ["ticker", "date"])

    op.create_table(
        "cash_flows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("flow_type", sa.String(32), nullable=False),
        sa.Column("broker", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("import_id", UUID, sa.ForeignKey("imports.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_cash_flows_date", "cash_flows", ["date"])
    op.create_index("ix_cash_flows_flow_type", "cash_flows", ["flow_type"])

    op.create_table(
        "isin_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("isin", sa.String(32), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("isin", "ticker", "source", name="uq_isin_mapping"),
    )
    op.create_index("ix_isin_mappings_isin", "isin_mappings", ["isin"])
    op.create_index("ix_isin_mappings_ticker", "isin_mappings", ["ticker"])

    op.drop_index("ix_sell_recommendation_states_ticker", table_name="sell_recommendation_states")
    op.rename_table("sell_recommendation_states", "sell_recommendation_state")
    op.create_index("ix_sell_recommendation_state_ticker", "sell_recommendation_state", ["ticker"])

    op.create_table(
        "tranche_log",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("position_id", UUID, sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pct", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_tranche_log_ticker", "tranche_log", ["ticker"])
    op.create_index("ix_tranche_log_date", "tranche_log", ["date"])
    op.create_index("ix_tranche_log_ticker_date", "tranche_log", ["ticker", "date"])

    op.create_table(
        "institutional_13f_trends",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("cusip", sa.String(16), nullable=False),
        sa.Column("manager_cik", sa.String(32), nullable=False),
        sa.Column("manager_name", sa.String(255), nullable=False),
        sa.Column("report_period", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("market_value_usd", sa.Float(), nullable=True),
        sa.Column("shares_change_pct", sa.Float(), nullable=True),
        sa.Column("holders_count", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("raw_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("cusip", "manager_cik", "report_period", name="uq_13f_trend"),
    )
    op.create_index("ix_institutional_13f_trends_ticker", "institutional_13f_trends", ["ticker"])
    op.create_index("ix_institutional_13f_trends_cusip", "institutional_13f_trends", ["cusip"])
    op.create_index("ix_institutional_13f_trends_manager_cik", "institutional_13f_trends", ["manager_cik"])
    op.create_index("ix_institutional_13f_trends_report_period", "institutional_13f_trends", ["report_period"])
    op.create_index("ix_13f_trends_ticker_period", "institutional_13f_trends", ["ticker", "report_period"])

    op.create_table(
        "sec13f_cusip_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cusip", sa.String(16), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("cusip", "ticker", name="uq_sec13f_cusip_mapping"),
    )
    op.create_index("ix_sec13f_cusip_mappings_cusip", "sec13f_cusip_mappings", ["cusip"])
    op.create_index("ix_sec13f_cusip_mappings_ticker", "sec13f_cusip_mappings", ["ticker"])

    op.add_column("jobs", sa.Column("celery_task_id", sa.String(128), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("error_message", sa.Text(), nullable=False, server_default=""))
    op.add_column("jobs", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")))
    op.create_index("ix_jobs_celery_task_id", "jobs", ["celery_task_id"])
    op.create_index("ix_jobs_status_created_at", "jobs", ["status", "created_at"])

    op.add_column("app_settings", sa.Column("description", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("app_settings", "description")

    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
    op.drop_index("ix_jobs_celery_task_id", table_name="jobs")
    op.drop_column("jobs", "created_at")
    op.drop_column("jobs", "error_message")
    op.drop_column("jobs", "celery_task_id")

    op.drop_index("ix_sec13f_cusip_mappings_ticker", table_name="sec13f_cusip_mappings")
    op.drop_index("ix_sec13f_cusip_mappings_cusip", table_name="sec13f_cusip_mappings")
    op.drop_table("sec13f_cusip_mappings")

    op.drop_index("ix_13f_trends_ticker_period", table_name="institutional_13f_trends")
    op.drop_index("ix_institutional_13f_trends_report_period", table_name="institutional_13f_trends")
    op.drop_index("ix_institutional_13f_trends_manager_cik", table_name="institutional_13f_trends")
    op.drop_index("ix_institutional_13f_trends_cusip", table_name="institutional_13f_trends")
    op.drop_index("ix_institutional_13f_trends_ticker", table_name="institutional_13f_trends")
    op.drop_table("institutional_13f_trends")

    op.drop_index("ix_tranche_log_ticker_date", table_name="tranche_log")
    op.drop_index("ix_tranche_log_date", table_name="tranche_log")
    op.drop_index("ix_tranche_log_ticker", table_name="tranche_log")
    op.drop_table("tranche_log")

    op.drop_index("ix_sell_recommendation_state_ticker", table_name="sell_recommendation_state")
    op.rename_table("sell_recommendation_state", "sell_recommendation_states")
    op.create_index("ix_sell_recommendation_states_ticker", "sell_recommendation_states", ["ticker"])

    op.drop_index("ix_isin_mappings_ticker", table_name="isin_mappings")
    op.drop_index("ix_isin_mappings_isin", table_name="isin_mappings")
    op.drop_table("isin_mappings")

    op.drop_index("ix_cash_flows_flow_type", table_name="cash_flows")
    op.drop_index("ix_cash_flows_date", table_name="cash_flows")
    op.drop_table("cash_flows")

    op.drop_index("ix_transactions_ticker_date", table_name="transactions")
    op.drop_index("ix_transactions_external_id", table_name="transactions")
    op.drop_index("ix_transactions_transaction_type", table_name="transactions")
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_index("ix_transactions_ticker", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("ix_imports_status", table_name="imports")
    op.drop_index("ix_imports_source", table_name="imports")
    op.drop_table("imports")

    op.drop_column("positions", "closed_at")
    op.drop_column("positions", "opened_at")
    op.drop_column("positions", "account")
    op.drop_column("positions", "broker")

    op.drop_index("ix_rs_ratings_instrument_date", table_name="rs_ratings")
    op.drop_column("rs_ratings", "metadata_json")
    op.drop_column("rs_ratings", "percentile")

    op.drop_column("breadth_daily", "metadata_json")
    op.drop_column("breadth_daily", "new_lows")
    op.drop_column("breadth_daily", "new_highs")
    op.drop_column("breadth_daily", "pct_above_20sma")

    op.drop_index("ix_universe_members_universe_instrument", table_name="universe_members")
    op.drop_index("ix_universe_members_ticker", table_name="universe_members")
    op.drop_index("ix_universe_members_instrument_id", table_name="universe_members")
    op.drop_index("ix_universe_members_universe_id", table_name="universe_members")
    op.drop_table("universe_members")

    op.drop_index("ix_universes_is_active", table_name="universes")
    op.drop_index("ix_universes_key", table_name="universes")
    op.drop_table("universes")

    op.drop_index("ix_price_bars_instrument_date", table_name="price_bars")
    op.drop_column("price_bars", "created_at")
    op.drop_column("instruments", "updated_at")
    op.drop_column("instruments", "metadata_json")
