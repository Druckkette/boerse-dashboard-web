from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


def uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    yahoo_symbol: Mapped[str] = mapped_column(String(64), default="")
    isin: Mapped[str] = mapped_column(String(32), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    exchange: Mapped[str] = mapped_column(String(64), default="")
    asset_class: Mapped[str] = mapped_column(String(32), default="stock")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    sector: Mapped[str] = mapped_column(String(128), default="")
    industry: Mapped[str] = mapped_column(String(128), default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="instrument")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", "source", name="uq_price_bar"),
        Index("ix_price_bars_instrument_date", "instrument_id", "date"),
    )

    id: Mapped[str] = uuid_pk()
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    adj_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="yfinance")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    instrument: Mapped[Instrument] = relationship(back_populates="price_bars")


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UniverseMember(Base):
    __tablename__ = "universe_members"
    __table_args__ = (
        UniqueConstraint("universe_id", "instrument_id", "valid_from", name="uq_universe_member"),
        Index("ix_universe_members_universe_instrument", "universe_id", "instrument_id"),
    )

    id: Mapped[str] = uuid_pk()
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    weight: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UniverseSymbolMapping(Base):
    __tablename__ = "universe_symbol_mappings"
    __table_args__ = (
        UniqueConstraint("universe_key", "source_ticker", name="uq_universe_symbol_mapping"),
        Index("ix_universe_symbol_mappings_universe_status", "universe_key", "status"),
    )

    id: Mapped[str] = uuid_pk()
    universe_key: Mapped[str] = mapped_column(String(96), index=True)
    source_ticker: Mapped[str] = mapped_column(String(32), index=True)
    yahoo_symbol: Mapped[str] = mapped_column(String(64), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[str] = uuid_pk()
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    ampel_phase: Mapped[str] = mapped_column(String(32))
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    breadth_mode: Mapped[str] = mapped_column(String(32), default="wachsam")
    volatility_regime: Mapped[str] = mapped_column(String(64), default="Neutral")
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BreadthDaily(Base):
    __tablename__ = "breadth_daily"
    __table_args__ = (UniqueConstraint("universe", "date", name="uq_breadth_daily"),)

    id: Mapped[str] = uuid_pk()
    universe: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    advancers: Mapped[int] = mapped_column(Integer, default=0)
    decliners: Mapped[int] = mapped_column(Integer, default=0)
    ad_line: Mapped[float | None] = mapped_column(Float)
    mcclellan: Mapped[float | None] = mapped_column(Float)
    pct_above_20sma: Mapped[float | None] = mapped_column(Float)
    pct_above_50sma: Mapped[float | None] = mapped_column(Float)
    pct_above_200sma: Mapped[float | None] = mapped_column(Float)
    new_highs: Mapped[int] = mapped_column(Integer, default=0)
    new_lows: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class RsRating(Base):
    __tablename__ = "rs_ratings"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", "source", name="uq_rs_rating"),
        Index("ix_rs_ratings_instrument_date", "instrument_id", "date"),
        Index("ix_rs_ratings_source_date", "source", "date"),
    )

    id: Mapped[str] = uuid_pk()
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    percentile: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(64), default="computed")
    universe_size: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint("instrument_id", "as_of", "source", name="uq_fundamental_snapshot"),
        Index("ix_fundamental_snapshots_ticker_as_of", "ticker", "as_of"),
    )

    id: Mapped[str] = uuid_pk()
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    fiscal_period: Mapped[str] = mapped_column(String(32), default="")
    quarterly_eps_growth_pct: Mapped[float | None] = mapped_column(Float)
    annual_eps_growth_pct: Mapped[float | None] = mapped_column(Float)
    quarterly_revenue_growth_pct: Mapped[float | None] = mapped_column(Float)
    annual_revenue_growth_pct: Mapped[float | None] = mapped_column(Float)
    roe_pct: Mapped[float | None] = mapped_column(Float)
    profit_margin_pct: Mapped[float | None] = mapped_column(Float)
    trailing_eps: Mapped[float | None] = mapped_column(Float)
    quarterly_eps_accelerating: Mapped[bool | None] = mapped_column(Boolean)
    quarterly_revenue_accelerating: Mapped[bool | None] = mapped_column(Boolean)
    institutional_holders: Mapped[int | None] = mapped_column(Integer)
    institutional_ownership_pct: Mapped[float | None] = mapped_column(Float)
    next_earnings_date: Mapped[date | None] = mapped_column(Date)
    beta: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EarningsEvent(Base):
    __tablename__ = "earnings_events"
    __table_args__ = (
        UniqueConstraint("ticker", "event_date", "source", name="uq_earnings_event"),
        Index("ix_earnings_events_date_ticker", "event_date", "ticker"),
    )

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    fiscal_date_ending: Mapped[date | None] = mapped_column(Date)
    time: Mapped[str] = mapped_column(String(16), default="")
    eps_estimated: Mapped[float | None] = mapped_column(Float)
    eps_actual: Mapped[float | None] = mapped_column(Float)
    revenue_estimated: Mapped[float | None] = mapped_column(Float)
    revenue_actual: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="fmp")
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[str] = uuid_pk()
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    shares: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[date | None] = mapped_column(Date)
    pivot_tag: Mapped[date | None] = mapped_column(Date)
    stop_pct: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    broker: Mapped[str] = mapped_column(String(64), default="")
    account: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_ticker_date", "ticker", "date"),)

    id: Mapped[str] = uuid_pk()
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    transaction_type: Mapped[str] = mapped_column(String(32), index=True)
    shares: Mapped[float] = mapped_column(Float, default=0)
    price: Mapped[float | None] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0)
    tax: Mapped[float] = mapped_column(Float, default=0)
    gross_amount: Mapped[float | None] = mapped_column(Float)
    net_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    broker: Mapped[str] = mapped_column(String(64), default="")
    external_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id"), nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CashFlow(Base):
    __tablename__ = "cash_flows"

    id: Mapped[str] = uuid_pk()
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    flow_type: Mapped[str] = mapped_column(String(32), index=True)
    broker: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    import_id: Mapped[str | None] = mapped_column(ForeignKey("imports.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    __tablename__ = "imports"

    id: Mapped[str] = uuid_pk()
    source: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IsinMapping(Base):
    __tablename__ = "isin_mappings"
    __table_args__ = (UniqueConstraint("isin", "ticker", "source", name="uq_isin_mapping"),)

    id: Mapped[str] = uuid_pk()
    isin: Mapped[str] = mapped_column(String(32), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SellManualInput(Base):
    __tablename__ = "sell_manual_inputs"

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    pivot: Mapped[float | None] = mapped_column(Float)
    low_day_1: Mapped[float | None] = mapped_column(Float)
    low_day_0: Mapped[float | None] = mapped_column(Float)
    market_environment: Mapped[str] = mapped_column(String(32), default="Unsicher")
    industry_group_status: Mapped[str] = mapped_column(String(32), default="Neutral")
    checkboxes_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    setup_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SellRecommendationState(Base):
    __tablename__ = "sell_recommendation_state"

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    last_seen_date: Mapped[date | None] = mapped_column(Date)
    last_pct: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_days: Mapped[int] = mapped_column(Integer, default=0)
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    snoozed_pct: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SellRankingSnapshot(Base):
    __tablename__ = "sell_ranking_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", name="uq_sell_ranking_snapshot_ticker"),
        Index("ix_sell_ranking_snapshots_status_recommendation", "status", "recommendation_pct"),
        Index("ix_sell_ranking_snapshots_generated_at", "generated_at"),
    )

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    pending_status: Mapped[str] = mapped_column(String(32), index=True)
    health_score: Mapped[float] = mapped_column(Float, default=0)
    recommendation_pct: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_job_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    item_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class TrancheLog(Base):
    __tablename__ = "tranche_log"
    __table_args__ = (Index("ix_tranche_log_ticker_date", "ticker", "date"),)

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    pct: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float | None] = mapped_column(Float)
    shares: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="api")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SellPostMortemNote(Base):
    __tablename__ = "sell_post_mortem_notes"
    __table_args__ = (
        UniqueConstraint("ticker", "check_key", name="uq_sell_post_mortem_ticker_check"),
        Index("ix_sell_post_mortem_ticker_status", "ticker", "status"),
    )

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    check_key: Mapped[str] = mapped_column(String(96), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TradeJournalEntry(Base):
    __tablename__ = "trade_journal_entries"
    __table_args__ = (
        Index("ix_trade_journal_ticker_type_status", "ticker", "entry_type", "status"),
        Index("ix_trade_journal_trade_date", "trade_date"),
        Index("ix_trade_journal_linked_entry", "linked_entry_id"),
    )

    id: Mapped[str] = uuid_pk()
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    entry_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[float | None] = mapped_column(Float)
    shares: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    stop_distance_pct: Mapped[float | None] = mapped_column(Float)
    linked_entry_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    realized_pnl_eur: Mapped[float | None] = mapped_column(Float)
    realized_pnl_pct: Mapped[float | None] = mapped_column(Float)
    stop_deviation_pct: Mapped[float | None] = mapped_column(Float)
    basis_text: Mapped[str] = mapped_column(Text, default="")
    alternative_entry: Mapped[bool] = mapped_column(Boolean, default=False)
    alternative_entry_text: Mapped[str] = mapped_column(Text, default="")
    primary_reasons: Mapped[str] = mapped_column(Text, default="")
    sell_reason: Mapped[str] = mapped_column(Text, default="")
    questionnaire_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    stock_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    market_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    portfolio_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    chart_images_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Institutional13FTrend(Base):
    __tablename__ = "institutional_13f_trends"
    __table_args__ = (
        UniqueConstraint("cusip", "manager_cik", "report_period", name="uq_13f_trend"),
        Index("ix_13f_trends_ticker_period", "ticker", "report_period"),
    )

    id: Mapped[str] = uuid_pk()
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True, default="")
    cusip: Mapped[str] = mapped_column(String(16), index=True)
    manager_cik: Mapped[str] = mapped_column(String(32), index=True)
    manager_name: Mapped[str] = mapped_column(String(255), default="")
    report_period: Mapped[date] = mapped_column(Date, index=True)
    filing_date: Mapped[date | None] = mapped_column(Date)
    shares: Mapped[float | None] = mapped_column(Float)
    market_value_usd: Mapped[float | None] = mapped_column(Float)
    shares_change_pct: Mapped[float | None] = mapped_column(Float)
    holders_count: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(Text, default="")
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sec13fCusipMapping(Base):
    __tablename__ = "sec13f_cusip_mappings"
    __table_args__ = (UniqueConstraint("cusip", "ticker", name="uq_sec13f_cusip_mapping"),)

    id: Mapped[str] = uuid_pk()
    cusip: Mapped[str] = mapped_column(String(16), index=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id"), nullable=True)
    issuer_name: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(64), default="sec13f")
    confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_status_heartbeat_at", "status", "heartbeat_at"),
    )

    id: Mapped[str] = uuid_pk()
    job_id: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    celery_task_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(255), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(96), default="")
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
