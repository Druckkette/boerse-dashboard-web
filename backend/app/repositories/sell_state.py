from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import SellManualInput as SellManualInputModel
from app.db.models import SellPostMortemNote as SellPostMortemNoteModel
from app.db.models import SellRankingSnapshot as SellRankingSnapshotModel
from app.db.models import SellRecommendationState as SellRecommendationStateModel
from app.db.models import TrancheLog as TrancheLogModel
from app.db.session import SessionLocal
from app.domain.sell.schemas import (
    SellManualInput,
    SellPositionRankingItem,
    SellPostMortemNote,
    SellRecommendationState,
    TrancheLogEntry,
)


class SellStateRepositoryUnavailable(RuntimeError):
    pass


_MEMORY_MANUAL_INPUTS: dict[str, SellManualInput] = {}
_MEMORY_TRANCHE_LOG: dict[str, list[TrancheLogEntry]] = {}
_MEMORY_RECOMMENDATION_STATE: dict[str, SellRecommendationState] = {}
_MEMORY_POST_MORTEM_NOTES: dict[str, dict[str, SellPostMortemNote]] = {}
_MEMORY_RANKING_SNAPSHOT: dict[str, tuple[SellPositionRankingItem, datetime, str]] = {}


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


def list_ranking_snapshot() -> tuple[list[SellPositionRankingItem], datetime | None, str]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(SellRankingSnapshotModel).order_by(
                    SellRankingSnapshotModel.status.asc(),
                    SellRankingSnapshotModel.recommendation_pct.desc(),
                    SellRankingSnapshotModel.health_score.asc(),
                    SellRankingSnapshotModel.ticker.asc(),
                )
            ).all()
            items = [_ranking_item_from_model(row) for row in rows]
            generated_at = max((row.generated_at for row in rows if row.generated_at), default=None)
            source_job_id = next((row.source_job_id for row in rows if row.source_job_id), "")
            return items, generated_at, source_job_id
    except SQLAlchemyError:
        if not _MEMORY_RANKING_SNAPSHOT:
            return [], None, ""
        rows = sorted(
            _MEMORY_RANKING_SNAPSHOT.values(),
            key=lambda item: (
                {"Verkaufen": 0, "Beobachten": 1, "Halten": 2}.get(item[0].status, 3),
                -item[0].recommendation_pct,
                item[0].health_score,
                item[0].ticker,
            ),
        )
        generated_at = max((item[1] for item in rows), default=None)
        source_job_id = next((item[2] for item in rows if item[2]), "")
        return [item[0] for item in rows], generated_at, source_job_id


def upsert_ranking_snapshot(
    items: list[SellPositionRankingItem],
    *,
    generated_at: datetime | None = None,
    source_job_id: str = "",
    replace_all: bool = False,
) -> int:
    now = generated_at or datetime.now(UTC)
    normalized = [item.model_copy(update={"ticker": _clean_ticker(item.ticker)}) for item in items if item.ticker]
    try:
        with SessionLocal() as db:
            if replace_all:
                db.execute(delete(SellRankingSnapshotModel))
            for item in normalized:
                row = db.scalars(
                    select(SellRankingSnapshotModel).where(SellRankingSnapshotModel.ticker == item.ticker)
                ).first()
                if row is None:
                    row = SellRankingSnapshotModel(ticker=item.ticker)
                    db.add(row)
                row.name = item.name
                row.status = item.status
                row.pending_status = item.pending_status
                row.health_score = item.health_score
                row.recommendation_pct = item.recommendation_pct
                row.generated_at = now
                row.source_job_id = source_job_id
                row.item_json = item.model_dump(mode="json")
            db.commit()
            return len(normalized)
    except SQLAlchemyError:
        if replace_all:
            _MEMORY_RANKING_SNAPSHOT.clear()
        for item in normalized:
            _MEMORY_RANKING_SNAPSHOT[item.ticker] = (item, now, source_job_id)
        return len(normalized)


def list_post_mortem_notes(ticker: str) -> list[SellPostMortemNote]:
    clean = _clean_ticker(ticker)
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(SellPostMortemNoteModel)
                .where(SellPostMortemNoteModel.ticker == clean)
                .order_by(SellPostMortemNoteModel.updated_at.desc())
            ).all()
            return [_post_mortem_note_from_model(row) for row in rows]
    except SQLAlchemyError:
        return list(_MEMORY_POST_MORTEM_NOTES.get(clean, {}).values())


def upsert_post_mortem_note(note: SellPostMortemNote) -> SellPostMortemNote:
    clean = _clean_ticker(note.ticker)
    check_key = str(note.check_key or "").strip()
    now = datetime.now(UTC)
    stored = note.model_copy(
        update={
            "ticker": clean,
            "check_key": check_key,
            "updated_at": now,
        }
    )
    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(SellPostMortemNoteModel).where(
                    SellPostMortemNoteModel.ticker == clean,
                    SellPostMortemNoteModel.check_key == check_key,
                )
            ).first()
            if row is None:
                row = SellPostMortemNoteModel(
                    ticker=clean,
                    check_key=check_key,
                    created_at=stored.created_at,
                )
                db.add(row)
            row.note = stored.note
            row.action = stored.action
            row.status = stored.status
            row.updated_at = now
            db.commit()
            db.refresh(row)
            return _post_mortem_note_from_model(row)
    except SQLAlchemyError:
        memory_note = stored
        if not memory_note.id:
            memory_note = memory_note.model_copy(update={"id": str(uuid4()), "created_at": now})
        _MEMORY_POST_MORTEM_NOTES.setdefault(clean, {})[check_key] = memory_note
        return memory_note


def clear_memory_sell_state() -> None:
    _MEMORY_MANUAL_INPUTS.clear()
    _MEMORY_TRANCHE_LOG.clear()
    _MEMORY_RECOMMENDATION_STATE.clear()
    _MEMORY_POST_MORTEM_NOTES.clear()
    _MEMORY_RANKING_SNAPSHOT.clear()


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


def _ranking_item_from_model(row: SellRankingSnapshotModel) -> SellPositionRankingItem:
    payload = dict(row.item_json or {})
    payload.setdefault("ticker", row.ticker)
    payload.setdefault("name", row.name or row.ticker)
    payload.setdefault("status", row.status or "Halten")
    payload.setdefault("pending_status", row.pending_status or "halten")
    payload.setdefault("health_score", row.health_score or 0)
    payload.setdefault("recommendation_pct", row.recommendation_pct or 0)
    return SellPositionRankingItem.model_validate(payload)


def _post_mortem_note_from_model(row: SellPostMortemNoteModel) -> SellPostMortemNote:
    return SellPostMortemNote(
        id=str(row.id),
        ticker=row.ticker,
        check_key=row.check_key,
        note=row.note or "",
        action=row.action or "",
        status=row.status or "open",
        created_at=row.created_at,
        updated_at=row.updated_at,
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
