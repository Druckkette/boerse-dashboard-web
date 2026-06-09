"""initial skeleton

Revision ID: 0001_initial_skeleton
Revises:
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_skeleton"
down_revision = None
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("yahoo_symbol", sa.String(64), nullable=False),
        sa.Column("isin", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(64), nullable=False),
        sa.Column("asset_class", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("sector", sa.String(128), nullable=False),
        sa.Column("industry", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index("ix_instruments_ticker", "instruments", ["ticker"])
    op.create_index("ix_instruments_isin", "instruments", ["isin"])

    op.create_table(
        "positions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("buy_price", sa.Float(), nullable=False),
        sa.Column("buy_date", sa.Date(), nullable=True),
        sa.Column("pivot_tag", sa.Date(), nullable=True),
        sa.Column("stop_pct", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_positions_ticker", "positions", ["ticker"])
    op.create_index("ix_positions_is_open", "positions", ["is_open"])

    op.create_table(
        "price_bars",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.UniqueConstraint("instrument_id", "date", "source", name="uq_price_bar"),
    )
    op.create_index("ix_price_bars_instrument_id", "price_bars", ["instrument_id"])
    op.create_index("ix_price_bars_date", "price_bars", ["date"])

    op.create_table(
        "market_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ampel_phase", sa.String(32), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("breadth_mode", sa.String(32), nullable=False),
        sa.Column("volatility_regime", sa.String(64), nullable=False),
        sa.Column("metrics_json", JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("date"),
    )
    op.create_index("ix_market_snapshots_date", "market_snapshots", ["date"])

    op.create_table(
        "breadth_daily",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("universe", sa.String(64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("advancers", sa.Integer(), nullable=False),
        sa.Column("decliners", sa.Integer(), nullable=False),
        sa.Column("ad_line", sa.Float(), nullable=True),
        sa.Column("mcclellan", sa.Float(), nullable=True),
        sa.Column("pct_above_50sma", sa.Float(), nullable=True),
        sa.Column("pct_above_200sma", sa.Float(), nullable=True),
        sa.UniqueConstraint("universe", "date", name="uq_breadth_daily"),
    )
    op.create_index("ix_breadth_daily_universe", "breadth_daily", ["universe"])
    op.create_index("ix_breadth_daily_date", "breadth_daily", ["date"])

    op.create_table(
        "rs_ratings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("instrument_id", UUID, sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("universe_size", sa.Integer(), nullable=False),
        sa.UniqueConstraint("instrument_id", "date", "source", name="uq_rs_rating"),
    )
    op.create_index("ix_rs_ratings_instrument_id", "rs_ratings", ["instrument_id"])
    op.create_index("ix_rs_ratings_date", "rs_ratings", ["date"])

    op.create_table(
        "sell_manual_inputs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("pivot", sa.Float(), nullable=True),
        sa.Column("low_day_1", sa.Float(), nullable=True),
        sa.Column("low_day_0", sa.Float(), nullable=True),
        sa.Column("market_environment", sa.String(32), nullable=False),
        sa.Column("industry_group_status", sa.String(32), nullable=False),
        sa.Column("checkboxes_json", JSONB, nullable=False),
        sa.Column("setup_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index("ix_sell_manual_inputs_ticker", "sell_manual_inputs", ["ticker"])

    op.create_table(
        "sell_recommendation_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("last_seen_date", sa.Date(), nullable=True),
        sa.Column("last_pct", sa.Integer(), nullable=False),
        sa.Column("consecutive_days", sa.Integer(), nullable=False),
        sa.Column("snoozed_until", sa.Date(), nullable=True),
        sa.Column("snoozed_pct", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index(
        "ix_sell_recommendation_states_ticker", "sell_recommendation_states", ["ticker"]
    )

    op.create_table(
        "jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("job_id", sa.String(96), nullable=False),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(96), nullable=False),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("result_json", JSONB, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_jobs_job_id", "jobs", ["job_id"])
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_job_type", table_name="jobs")
    op.drop_index("ix_jobs_job_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(
        "ix_sell_recommendation_states_ticker", table_name="sell_recommendation_states"
    )
    op.drop_table("sell_recommendation_states")
    op.drop_index("ix_sell_manual_inputs_ticker", table_name="sell_manual_inputs")
    op.drop_table("sell_manual_inputs")
    op.drop_index("ix_rs_ratings_date", table_name="rs_ratings")
    op.drop_index("ix_rs_ratings_instrument_id", table_name="rs_ratings")
    op.drop_table("rs_ratings")
    op.drop_index("ix_breadth_daily_date", table_name="breadth_daily")
    op.drop_index("ix_breadth_daily_universe", table_name="breadth_daily")
    op.drop_table("breadth_daily")
    op.drop_index("ix_market_snapshots_date", table_name="market_snapshots")
    op.drop_table("market_snapshots")
    op.drop_index("ix_price_bars_date", table_name="price_bars")
    op.drop_index("ix_price_bars_instrument_id", table_name="price_bars")
    op.drop_table("price_bars")
    op.drop_index("ix_positions_is_open", table_name="positions")
    op.drop_index("ix_positions_ticker", table_name="positions")
    op.drop_table("positions")
    op.drop_index("ix_instruments_isin", table_name="instruments")
    op.drop_index("ix_instruments_ticker", table_name="instruments")
    op.drop_table("instruments")
