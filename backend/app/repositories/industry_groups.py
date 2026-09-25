from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    IndustryGroup,
    IndustryGroupMembership,
    IndustryGroupRule,
    Instrument,
    Universe,
    UniverseMember,
)
from app.db.session import SessionLocal


class IndustryGroupRepositoryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class InstrumentClassificationRow:
    instrument_id: str
    ticker: str
    name: str
    sector: str
    industry: str
    exchange: str
    metadata_json: dict


def list_universe_instruments(key: str = "us_common_stocks") -> list[InstrumentClassificationRow]:
    try:
        with SessionLocal() as db:
            universe = db.scalar(select(Universe).where(Universe.key == key))
            if universe is None:
                return []
            rows = db.execute(
                select(Instrument)
                .join(UniverseMember, UniverseMember.instrument_id == Instrument.id)
                .where(
                    UniverseMember.universe_id == universe.id,
                    UniverseMember.valid_to.is_(None),
                )
                .order_by(Instrument.ticker.asc())
            ).scalars().all()
            return [
                InstrumentClassificationRow(
                    instrument_id=row.id,
                    ticker=row.ticker,
                    name=row.name or "",
                    sector=row.sector or "",
                    industry=row.industry or "",
                    exchange=row.exchange or "",
                    metadata_json=row.metadata_json or {},
                )
                for row in rows
            ]
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def get_membership_map() -> dict[str, IndustryGroupMembership]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(select(IndustryGroupMembership)).all()
            return {row.ticker.upper(): row for row in rows}
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def get_or_create_group(
    *,
    group_code: str,
    name: str,
    sector: str,
    industry_family: str,
    taxonomy_version: str,
    description: str = "",
) -> str:
    try:
        with SessionLocal() as db:
            row = db.scalar(
                select(IndustryGroup).where(
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroup.group_code == group_code,
                )
            )
            if row is None:
                row = IndustryGroup(
                    group_code=group_code,
                    name=name,
                    sector=sector,
                    industry_family=industry_family,
                    description=description,
                    taxonomy_version=taxonomy_version,
                    active=True,
                )
                db.add(row)
            else:
                row.name = name
                row.sector = sector
                row.industry_family = industry_family
                row.description = description or row.description
                row.active = True
            db.commit()
            db.refresh(row)
            return row.id
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def upsert_exact_industry_rule(
    *,
    normalized_industry: str,
    group_id: str,
    confidence: float,
    taxonomy_version: str,
) -> None:
    if not normalized_industry:
        return
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(IndustryGroupRule).where(
                    IndustryGroupRule.taxonomy_version == taxonomy_version,
                    IndustryGroupRule.active.is_(True),
                    IndustryGroupRule.source == "provider_industry_exact",
                )
            ).all()
            for row in rows:
                if (row.metadata_json or {}).get("normalized_industry") == normalized_industry:
                    row.target_group_id = group_id
                    row.confidence = confidence
                    db.commit()
                    return
            db.add(
                IndustryGroupRule(
                    priority=500,
                    target_group_id=group_id,
                    confidence=confidence,
                    source="provider_industry_exact",
                    active=True,
                    taxonomy_version=taxonomy_version,
                    metadata_json={"normalized_industry": normalized_industry},
                )
            )
            db.commit()
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def exact_industry_rule(normalized_industry: str, taxonomy_version: str) -> tuple[str, float] | None:
    if not normalized_industry:
        return None
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(IndustryGroupRule).where(
                    IndustryGroupRule.taxonomy_version == taxonomy_version,
                    IndustryGroupRule.active.is_(True),
                    IndustryGroupRule.source == "provider_industry_exact",
                )
            ).all()
            for row in rows:
                if (row.metadata_json or {}).get("normalized_industry") == normalized_industry:
                    return row.target_group_id, float(row.confidence)
            return None
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def group_by_id(group_id: str) -> IndustryGroup | None:
    try:
        with SessionLocal() as db:
            return db.get(IndustryGroup, group_id)
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def upsert_membership(
    *,
    instrument_id: str,
    ticker: str,
    industry_group_id: str | None,
    status: str,
    classification_source: str,
    classification_confidence: float | None,
    classification_fingerprint: str,
    sector_snapshot: str,
    industry_snapshot: str,
    sic_snapshot: str,
    assignment_version: str,
    explanation_json: dict,
) -> None:
    try:
        with SessionLocal() as db:
            row = db.scalar(
                select(IndustryGroupMembership).where(
                    IndustryGroupMembership.instrument_id == instrument_id
                )
            )
            if row is not None and row.is_manual_override:
                row.last_verified_at = datetime.now(UTC)
                db.commit()
                return
            if row is None:
                row = IndustryGroupMembership(instrument_id=instrument_id, ticker=ticker)
                db.add(row)
            row.ticker = ticker
            row.industry_group_id = industry_group_id
            row.status = status
            row.classification_source = classification_source
            row.classification_confidence = classification_confidence
            row.classification_fingerprint = classification_fingerprint
            row.sector_snapshot = sector_snapshot
            row.industry_snapshot = industry_snapshot
            row.sic_snapshot = sic_snapshot
            row.assignment_version = assignment_version
            row.explanation_json = explanation_json
            row.last_verified_at = datetime.now(UTC)
            db.commit()
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def set_manual_override(*, ticker: str, group_id: str, reason: str, taxonomy_version: str) -> None:
    clean = ticker.strip().upper()
    try:
        with SessionLocal() as db:
            instrument = db.scalar(select(Instrument).where(Instrument.ticker == clean))
            if instrument is None:
                raise ValueError(f"Unknown instrument: {clean}")
            group = db.get(IndustryGroup, group_id)
            if group is None or group.taxonomy_version != taxonomy_version:
                raise ValueError("Unknown industry group for active taxonomy")
            row = db.scalar(select(IndustryGroupMembership).where(IndustryGroupMembership.instrument_id == instrument.id))
            if row is None:
                row = IndustryGroupMembership(instrument_id=instrument.id, ticker=clean)
                db.add(row)
            row.industry_group_id = group.id
            row.status = "classified"
            row.classification_source = "manual_override"
            row.classification_confidence = 1.0
            row.assignment_version = taxonomy_version
            row.is_manual_override = True
            row.override_reason = reason
            row.override_at = datetime.now(UTC)
            row.last_verified_at = datetime.now(UTC)
            db.commit()
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def diagnostics(taxonomy_version: str) -> dict:
    try:
        with SessionLocal() as db:
            groups = db.scalars(
                select(IndustryGroup).where(
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroup.active.is_(True),
                )
            ).all()
            memberships = db.scalars(
                select(IndustryGroupMembership).where(
                    IndustryGroupMembership.assignment_version == taxonomy_version
                )
            ).all()
            counts: dict[str, int] = {}
            for row in memberships:
                if row.industry_group_id:
                    counts[row.industry_group_id] = counts.get(row.industry_group_id, 0) + 1
            group_rows = [
                {
                    "id": group.id,
                    "group_code": group.group_code,
                    "name": group.name,
                    "sector": group.sector,
                    "industry_family": group.industry_family,
                    "member_count": counts.get(group.id, 0),
                }
                for group in groups
            ]
            return {
                "number_of_groups": len(groups),
                "classified": sum(row.status == "classified" for row in memberships),
                "needs_review": sum(row.status == "needs_review" for row in memberships),
                "excluded": sum(row.status == "excluded" for row in memberships),
                "high_confidence": sum((row.classification_confidence or 0) >= 0.80 for row in memberships if row.status == "classified"),
                "medium_confidence": sum(0.65 <= (row.classification_confidence or 0) < 0.80 for row in memberships if row.status == "classified"),
                "groups": sorted(group_rows, key=lambda item: (-item["member_count"], item["name"])),
            }
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def review_queue(limit: int = 500) -> list[dict]:
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroupMembership, Instrument)
                .join(Instrument, Instrument.id == IndustryGroupMembership.instrument_id)
                .where(IndustryGroupMembership.status == "needs_review")
                .order_by(IndustryGroupMembership.classification_confidence.asc().nullsfirst(), Instrument.ticker.asc())
                .limit(max(1, min(limit, 5000)))
            ).all()
            return [
                {
                    "ticker": instrument.ticker,
                    "name": instrument.name,
                    "sector": instrument.sector,
                    "industry": instrument.industry,
                    "sic": membership.sic_snapshot,
                    "suggested_group_id": membership.industry_group_id,
                    "confidence": membership.classification_confidence,
                    "explanation": membership.explanation_json,
                }
                for membership, instrument in rows
            ]
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def membership_export_rows(taxonomy_version: str) -> list[dict]:
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroupMembership, Instrument, IndustryGroup)
                .join(Instrument, Instrument.id == IndustryGroupMembership.instrument_id)
                .outerjoin(IndustryGroup, IndustryGroup.id == IndustryGroupMembership.industry_group_id)
                .where(IndustryGroupMembership.assignment_version == taxonomy_version)
                .order_by(Instrument.ticker.asc())
            ).all()
            return [
                {
                    "ticker": instrument.ticker,
                    "name": instrument.name,
                    "sector": membership.sector_snapshot,
                    "original_industry": membership.industry_snapshot,
                    "sic": membership.sic_snapshot,
                    "sic_description": (instrument.metadata_json or {}).get("sec_sic_description", ""),
                    "industry_group": group.name if group else "",
                    "industry_family": group.industry_family if group else "",
                    "confidence": membership.classification_confidence,
                    "classification_source": membership.classification_source,
                    "assignment_version": membership.assignment_version,
                    "manual_override": membership.is_manual_override,
                    "status": membership.status,
                }
                for membership, instrument, group in rows
            ]
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc
