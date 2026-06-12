from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument, Universe, UniverseMember
from app.db.session import SessionLocal


@dataclass(frozen=True)
class UniverseStatusRow:
    key: str
    name: str
    source: str
    member_count: int
    updated_at: datetime | None
    sample_tickers: list[str]
    metadata_json: dict


class UniverseRepositoryUnavailable(RuntimeError):
    pass


def upsert_universe_members(
    *,
    key: str,
    name: str,
    source: str,
    tickers: list[str],
    metadata: dict | None = None,
) -> UniverseStatusRow:
    clean_key = key.strip()
    clean_tickers = list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))
    if not clean_key or not clean_tickers:
        raise ValueError("Universe key and tickers are required.")

    today = date.today()
    now = datetime.now(UTC)
    try:
        with SessionLocal() as db:
            universe = db.scalars(select(Universe).where(Universe.key == clean_key)).first()
            if universe is None:
                universe = Universe(
                    key=clean_key,
                    name=name,
                    source=source,
                    description="",
                    is_active=True,
                    metadata_json={},
                )
                db.add(universe)
                db.flush()
            universe.name = name or universe.name or clean_key
            universe.source = source or universe.source
            universe.metadata_json = {**(metadata or {}), "member_count": len(clean_tickers), "updated_at": now.isoformat()}

            instruments = db.scalars(select(Instrument).where(Instrument.ticker.in_(clean_tickers))).all()
            by_ticker = {instrument.ticker.upper(): instrument for instrument in instruments}
            for ticker in clean_tickers:
                if ticker in by_ticker:
                    continue
                instrument = Instrument(ticker=ticker, yahoo_symbol=ticker, name=ticker, currency="USD")
                db.add(instrument)
                db.flush()
                by_ticker[ticker] = instrument

            existing = db.scalars(
                select(UniverseMember).where(UniverseMember.universe_id == universe.id, UniverseMember.valid_to.is_(None))
            ).all()
            existing_by_ticker = {row.ticker.upper(): row for row in existing}
            target = set(clean_tickers)
            for row in existing:
                if row.ticker.upper() not in target:
                    row.valid_to = today
            for ticker in clean_tickers:
                row = existing_by_ticker.get(ticker)
                if row is None or row.valid_to is not None:
                    db.add(
                        UniverseMember(
                            universe_id=universe.id,
                            instrument_id=by_ticker[ticker].id,
                            ticker=ticker,
                            valid_from=today,
                            valid_to=None,
                            weight=None,
                            metadata_json={},
                        )
                    )
            db.commit()
            return get_universe_status(clean_key) or UniverseStatusRow(
                key=clean_key,
                name=name,
                source=source,
                member_count=len(clean_tickers),
                updated_at=now,
                sample_tickers=clean_tickers[:20],
                metadata_json=metadata or {},
            )
    except SQLAlchemyError as exc:
        raise UniverseRepositoryUnavailable(str(exc)) from exc


def get_universe_status(key: str = "us_common_stocks") -> UniverseStatusRow | None:
    try:
        with SessionLocal() as db:
            universe = db.scalars(select(Universe).where(Universe.key == key)).first()
            if universe is None:
                return None
            member_count = db.scalar(
                select(func.count(UniverseMember.id)).where(
                    UniverseMember.universe_id == universe.id,
                    UniverseMember.valid_to.is_(None),
                )
            )
            latest_created_at = db.scalar(
                select(func.max(UniverseMember.created_at)).where(UniverseMember.universe_id == universe.id)
            )
            sample = db.scalars(
                select(UniverseMember.ticker)
                .where(UniverseMember.universe_id == universe.id, UniverseMember.valid_to.is_(None))
                .order_by(UniverseMember.ticker.asc())
                .limit(30)
            ).all()
            return UniverseStatusRow(
                key=universe.key,
                name=universe.name,
                source=universe.source,
                member_count=int(member_count or 0),
                updated_at=latest_created_at,
                sample_tickers=list(sample),
                metadata_json=universe.metadata_json or {},
            )
    except SQLAlchemyError as exc:
        raise UniverseRepositoryUnavailable(str(exc)) from exc


def list_universe_tickers(key: str = "us_common_stocks", *, limit: int = 5000) -> list[str]:
    try:
        with SessionLocal() as db:
            universe = db.scalars(select(Universe).where(Universe.key == key)).first()
            if universe is None:
                return []
            rows = db.scalars(
                select(UniverseMember.ticker)
                .where(UniverseMember.universe_id == universe.id, UniverseMember.valid_to.is_(None))
                .order_by(UniverseMember.ticker.asc())
                .limit(max(1, min(10_000, limit)))
            ).all()
            return list(rows)
    except SQLAlchemyError as exc:
        raise UniverseRepositoryUnavailable(str(exc)) from exc
