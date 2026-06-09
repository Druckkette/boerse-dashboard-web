from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import SellManualInput as SellManualInputModel
from app.db.models import SellRecommendationState as SellRecommendationStateModel
from app.db.models import TrancheLog as TrancheLogModel
from app.db.session import SessionLocal
from app.domain.sell.schemas import SellManualInput, SellRecommendationState, TrancheLogEntry


class SellStateRepositoryUnavailable(RuntimeError):
    pass


_MEMORY_MANUAL_INPUTS: dict[str, SellManualInput] = {}
_MEMORY_TRANCHE_LOG: dict[str, list[TrancheLogEntry]] = {}
_MEMORY_RECOMMENDATION_STATE: dict[str, SellRecommendationState] = {}


def get_manual_input(ticker: str) -> SellManualInput | None:
    clean = _clean_ticker(ticker)
    try:
        with SessionLocal() as db:
            row = db.scalars(select(SellManualInputModel).where(SellManualInputModel.ticker == clean)).first()
            return _manual_from_model(row) if row else None
    except SQLAlchemyError:
        return _MEMORY_MANUAL_INPUTS.get(clean)


def upsert_manual_input(manual: SellManualInput) -> SellManualInput:
    clean = _clean_ticker(manual.ticker)
    stored = manual.model_copy(update={"ticker": clean})
    try:
        with SessionLocal() as db:
            row = db.scalars(select(SellManualInputModel).where(SellManualInputModel.ticker == clean)).first()
            if row is None:
                row = SellManualInputModel(ticker=clean)
                db.add(row)
            row.pivot = stored.pivot
            row.low_day_1 = stored.low_day_1
            row.low_day_0 = stored.low_day_0
            row.market_environment = stored.market_environment
            row.industry_group_status = stored.industry_group_status
            row.checkboxes_json = {
                "personality_changed": stored.personality_changed,
                "strength_checkboxes": stored.strength_checkboxes,
                "warning_checkboxes": stored.warning_checkboxes,
            }
            row.setup_json = stored.sell_setup
            db.commit()
            return stored
    except SQLAlchemyError:
        _MEMORY_MANUAL_INPUTS[clean] = stored
        return stored


def list_tranche_log(ticker: str) -> list[TrancheLogEntry]:
    clean = _clean_ticker(ticker)
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(TrancheLogModel)
                .where(TrancheLogModel.ticker == clean)
                .order_by(TrancheLogModel.date.asc(), TrancheLogModel.created_at.asc())
            ).all()
            return [_tranche_from_model(row) for row in rows]
    except SQLAlchemyError:
        return list(_MEMORY_TRANCHE_LOG.get(clean, []))


def create_tranche_log_entry(entry: TrancheLogEntry) -> TrancheLogEntry:
    clean = _clean_ticker(entry.ticker)
    stored = entry.model_copy(update={"ticker": clean, "source": entry.source or "api"})
    try:
        with SessionLocal() as db:
            row = TrancheLogModel(
                ticker=clean,
                date=_parse_date(stored.date) or date.today(),
                pct=stored.pct,
                reason=stored.reason,
                price=stored.price,
                shares=stored.shares,
                source=stored.source,
                created_at=stored.created_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _tranche_from_model(row)
    except SQLAlchemyError:
        _MEMORY_TRANCHE_LOG.setdefault(clean, []).append(stored)
        return stored


def get_recommendation_state(ticker: str) -> SellRecommendationState | None:
    clean = _clean_ticker(ticker)
    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(SellRecommendationStateModel).where(SellRecommendationStateModel.ticker == clean)
            ).first()
            return _state_from_model(row) if row else None
    except SQLAlchemyError:
        return _MEMORY_RECOMMENDATION_STATE.get(clean)


def upsert_recommendation_state(ticker: str, state: SellRecommendationState) -> SellRecommendationState:
    clean = _clean_ticker(ticker)
    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(SellRecommendationStateModel).where(SellRecommendationStateModel.ticker == clean)
            ).first()
            if row is None:
                row = SellRecommendationStateModel(ticker=clean)
                db.add(row)
            row.last_seen_date = _parse_date(state.last_seen_date)
            row.last_pct = state.last_pct
            row.consecutive_days = state.consecutive_days
            row.snoozed_until = _parse_date(state.snoozed_until)
            row.snoozed_pct = state.snoozed_pct
            db.commit()
            return state
    except SQLAlchemyError:
        _MEMORY_RECOMMENDATION_STATE[clean] = state
        return state


def clear_memory_sell_state() -> None:
    _MEMORY_MANUAL_INPUTS.clear()
    _MEMORY_TRANCHE_LOG.clear()
    _MEMORY_RECOMMENDATION_STATE.clear()


def _manual_from_model(row: SellManualInputModel) -> SellManualInput:
    checkboxes = row.checkboxes_json or {}
    return SellManualInput(
        ticker=row.ticker,
        pivot=row.pivot,
        low_day_1=row.low_day_1,
        low_day_0=row.low_day_0,
        market_environment=row.market_environment or "Unsicher",
        industry_group_status=row.industry_group_status or "Neutral",
        personality_changed=bool(checkboxes.get("personality_changed") or False),
        strength_checkboxes=dict(checkboxes.get("strength_checkboxes") or {}),
        warning_checkboxes=dict(checkboxes.get("warning_checkboxes") or {}),
        sell_setup=dict(row.setup_json or {}),
    )


def _tranche_from_model(row: TrancheLogModel) -> TrancheLogEntry:
    return TrancheLogEntry(
        ticker=row.ticker,
        date=row.date.isoformat(),
        pct=row.pct,
        reason=row.reason or "",
        price=row.price,
        shares=row.shares,
        source=row.source or "api",
        created_at=row.created_at,
    )


def _state_from_model(row: SellRecommendationStateModel) -> SellRecommendationState:
    return SellRecommendationState(
        last_seen_date=row.last_seen_date.isoformat() if row.last_seen_date else "",
        last_pct=row.last_pct,
        consecutive_days=row.consecutive_days,
        snoozed_until=row.snoozed_until.isoformat() if row.snoozed_until else "",
        snoozed_pct=row.snoozed_pct,
    )


def _parse_date(value: str | date | None) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _clean_ticker(ticker: str) -> str:
    return str(ticker or "").upper().strip()
