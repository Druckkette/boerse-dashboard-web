from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument, Universe, UniverseMember, UniverseSymbolMapping
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


@dataclass(frozen=True)
class UniverseSymbolMappingRow:
    universe_key: str
    source_ticker: str
    yahoo_symbol: str
    status: str
    source: str
    note: str
    confidence: float | None
    updated_at: datetime | None


@dataclass(frozen=True)
class ResolvedUniverseSymbolRow:
    source_ticker: str
    yahoo_symbol: str
    status: str
    source: str


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


def list_symbol_mappings(
    key: str = "us_common_stocks",
    *,
    limit: int = 500,
) -> list[UniverseSymbolMappingRow]:
    clean_key = key.strip() or "us_common_stocks"
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(UniverseSymbolMapping)
                .where(UniverseSymbolMapping.universe_key == clean_key)
                .order_by(UniverseSymbolMapping.source_ticker.asc())
                .limit(max(1, min(10_000, limit)))
            ).all()
            return [_mapping_row(row) for row in rows]
    except SQLAlchemyError as exc:
        raise UniverseRepositoryUnavailable(str(exc)) from exc


def upsert_symbol_mapping(
    *,
    key: str,
    source_ticker: str,
    yahoo_symbol: str,
    status: str = "active",
    source: str = "manual",
    note: str = "",
    confidence: float | None = 1.0,
) -> UniverseSymbolMappingRow:
    clean_key = key.strip() or "us_common_stocks"
    clean_source = _normalize_symbol(source_ticker)
    clean_yahoo = yahoo_symbol.strip().upper()
    clean_status = status if status in {"active", "ignored"} else "active"
    if not clean_source:
        raise ValueError("source_ticker is required.")
    if clean_status == "active" and not clean_yahoo:
        clean_yahoo = clean_source

    try:
        with SessionLocal() as db:
            row = db.scalars(
                select(UniverseSymbolMapping).where(
                    UniverseSymbolMapping.universe_key == clean_key,
                    UniverseSymbolMapping.source_ticker == clean_source,
                )
            ).first()
            if row is None:
                row = UniverseSymbolMapping(
                    universe_key=clean_key,
                    source_ticker=clean_source,
                    yahoo_symbol=clean_yahoo,
                    status=clean_status,
                    source=source,
                    note=note,
                    confidence=confidence,
                    metadata_json={},
                )
                db.add(row)
            else:
                row.yahoo_symbol = clean_yahoo
                row.status = clean_status
                row.source = source or row.source
                row.note = note
                row.confidence = confidence
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == clean_source)).first()
            if instrument is not None and clean_yahoo:
                instrument.yahoo_symbol = clean_yahoo
            db.commit()
            db.refresh(row)
            return _mapping_row(row)
    except SQLAlchemyError as exc:
        raise UniverseRepositoryUnavailable(str(exc)) from exc


def list_resolved_universe_symbols(
    key: str = "us_common_stocks",
    *,
    limit: int = 5000,
) -> list[ResolvedUniverseSymbolRow]:
    clean_key = key.strip() or "us_common_stocks"
    tickers = list_universe_tickers(clean_key, limit=limit)
    if not tickers:
        return []
    mappings = {
        row.source_ticker.upper(): row
        for row in list_symbol_mappings(clean_key, limit=max(limit, 500))
    }
    resolved: list[ResolvedUniverseSymbolRow] = []
    for ticker in tickers:
        mapping = mappings.get(ticker.upper())
        if mapping is not None:
            if mapping.status == "ignored":
                continue
            yahoo_symbol = mapping.yahoo_symbol or ticker
            resolved.append(
                ResolvedUniverseSymbolRow(
                    source_ticker=ticker,
                    yahoo_symbol=yahoo_symbol,
                    status=mapping.status,
                    source=mapping.source,
                )
            )
            continue
        resolved.append(
            ResolvedUniverseSymbolRow(
                source_ticker=ticker,
                yahoo_symbol=ticker,
                status="unmapped",
                source="universe",
            )
        )
    return resolved[:limit]


def _mapping_row(row: UniverseSymbolMapping) -> UniverseSymbolMappingRow:
    return UniverseSymbolMappingRow(
        universe_key=row.universe_key,
        source_ticker=row.source_ticker,
        yahoo_symbol=row.yahoo_symbol or "",
        status=row.status or "active",
        source=row.source or "",
        note=row.note or "",
        confidence=row.confidence,
        updated_at=row.updated_at,
    )


def _normalize_symbol(value: str) -> str:
    return value.strip().upper().replace(".", "-")
