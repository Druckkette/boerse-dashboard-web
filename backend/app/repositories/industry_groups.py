from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
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


@dataclass(frozen=True)
class MembershipState:
    instrument_id: str
    ticker: str
    status: str
    classification_fingerprint: str
    assignment_version: str
    is_manual_override: bool


def list_universe_instruments(key: str = "us_common_stocks") -> list[InstrumentClassificationRow]:
    """Load the authoritative persisted universe membership in one query.

    Industry-group classification deliberately uses UniverseMember for
    us_common_stocks as its source of truth. External RS CSVs may enrich
    market/ranking data later but must never create a competing stock universe.
    """
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


def get_membership_map(instrument_ids: list[str] | None = None) -> dict[str, MembershipState]:
    try:
        with SessionLocal() as db:
            stmt = select(IndustryGroupMembership)
            if instrument_ids:
                stmt = stmt.where(IndustryGroupMembership.instrument_id.in_(instrument_ids))
            rows = db.scalars(stmt).all()
            return {
                row.ticker.upper(): MembershipState(
                    instrument_id=row.instrument_id,
                    ticker=row.ticker,
                    status=row.status,
                    classification_fingerprint=row.classification_fingerprint or "",
                    assignment_version=row.assignment_version or "",
                    is_manual_override=bool(row.is_manual_override),
                )
                for row in rows
            }
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def load_exact_industry_rule_map(taxonomy_version: str) -> dict[str, dict]:
    """Load all exact provider-industry mappings once for in-memory matching."""
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroupRule, IndustryGroup)
                .join(IndustryGroup, IndustryGroup.id == IndustryGroupRule.target_group_id)
                .where(
                    IndustryGroupRule.taxonomy_version == taxonomy_version,
                    IndustryGroupRule.active.is_(True),
                    IndustryGroupRule.source == "provider_industry_exact",
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroup.active.is_(True),
                )
            ).all()
            result: dict[str, dict] = {}
            for rule, group in rows:
                normalized = str((rule.metadata_json or {}).get("normalized_industry") or "").strip()
                if normalized:
                    result[normalized] = {
                        "group_code": group.group_code,
                        "group_name": group.name,
                        "sector": group.sector,
                        "industry_family": group.industry_family,
                        "confidence": float(rule.confidence),
                    }
            return result
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def persist_classification_batch(
    *,
    taxonomy_version: str,
    group_definitions: dict[str, dict],
    exact_industry_rules: dict[str, dict],
    memberships: list[dict],
) -> None:
    """Persist groups, derived rules and memberships in one transaction."""
    if not memberships and not group_definitions and not exact_industry_rules:
        return
    try:
        with SessionLocal() as db:
            group_codes = list(group_definitions)
            existing_groups = (
                db.scalars(
                    select(IndustryGroup).where(
                        IndustryGroup.taxonomy_version == taxonomy_version,
                        IndustryGroup.group_code.in_(group_codes),
                    )
                ).all()
                if group_codes
                else []
            )
            groups_by_code = {group.group_code: group for group in existing_groups}

            for code, definition in group_definitions.items():
                group = groups_by_code.get(code)
                if group is None:
                    group = IndustryGroup(group_code=code, taxonomy_version=taxonomy_version)
                    db.add(group)
                    groups_by_code[code] = group
                group.name = str(definition.get("name") or code)[:160]
                group.sector = str(definition.get("sector") or "")[:128]
                group.industry_family = str(definition.get("industry_family") or "")[:128]
                group.description = str(definition.get("description") or "")
                group.active = True
            db.flush()

            existing_rules = db.scalars(
                select(IndustryGroupRule).where(
                    IndustryGroupRule.taxonomy_version == taxonomy_version,
                    IndustryGroupRule.source == "provider_industry_exact",
                )
            ).all()
            rules_by_industry = {
                str((rule.metadata_json or {}).get("normalized_industry") or ""): rule
                for rule in existing_rules
                if (rule.metadata_json or {}).get("normalized_industry")
            }
            for normalized, definition in exact_industry_rules.items():
                group = groups_by_code.get(str(definition.get("group_code") or ""))
                if group is None:
                    continue
                rule = rules_by_industry.get(normalized)
                if rule is None:
                    rule = IndustryGroupRule(
                        priority=500,
                        source="provider_industry_exact",
                        taxonomy_version=taxonomy_version,
                        metadata_json={"normalized_industry": normalized},
                    )
                    db.add(rule)
                    rules_by_industry[normalized] = rule
                rule.target_group_id = group.id
                rule.confidence = float(definition.get("confidence") or 0.78)
                rule.active = True

            instrument_ids = [str(item["instrument_id"]) for item in memberships]
            existing_memberships = (
                db.scalars(
                    select(IndustryGroupMembership).where(
                        IndustryGroupMembership.instrument_id.in_(instrument_ids)
                    )
                ).all()
                if instrument_ids
                else []
            )
            memberships_by_instrument = {
                row.instrument_id: row for row in existing_memberships
            }
            now = datetime.now(UTC)

            for item in memberships:
                instrument_id = str(item["instrument_id"])
                row = memberships_by_instrument.get(instrument_id)
                if row is not None and row.is_manual_override:
                    row.last_verified_at = now
                    continue
                if row is None:
                    row = IndustryGroupMembership(
                        instrument_id=instrument_id,
                        ticker=str(item["ticker"]),
                    )
                    db.add(row)
                    memberships_by_instrument[instrument_id] = row

                group_code = str(item.get("group_code") or "")
                group = groups_by_code.get(group_code) if group_code else None
                row.ticker = str(item["ticker"])
                row.industry_group_id = group.id if group else None
                row.status = str(item["status"])
                row.classification_source = str(item.get("classification_source") or "")
                row.classification_confidence = item.get("classification_confidence")
                row.classification_fingerprint = str(item.get("classification_fingerprint") or "")
                row.sector_snapshot = str(item.get("sector_snapshot") or "")[:128]
                row.industry_snapshot = str(item.get("industry_snapshot") or "")[:160]
                row.sic_snapshot = str(item.get("sic_snapshot") or "")[:32]
                row.assignment_version = taxonomy_version
                row.explanation_json = item.get("explanation_json") or {}
                row.last_verified_at = now
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
            row = db.scalar(
                select(IndustryGroupMembership).where(
                    IndustryGroupMembership.instrument_id == instrument.id
                )
            )
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


def universe_diagnostics(instrument_ids: list[str], taxonomy_version: str) -> dict:
    if not instrument_ids:
        return {
            "number_of_groups": 0,
            "classified": 0,
            "needs_review": 0,
            "excluded": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "groups": [],
        }
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroupMembership, IndustryGroup)
                .outerjoin(IndustryGroup, IndustryGroup.id == IndustryGroupMembership.industry_group_id)
                .where(
                    IndustryGroupMembership.instrument_id.in_(instrument_ids),
                    IndustryGroupMembership.assignment_version == taxonomy_version,
                )
            ).all()
            counts: dict[str, dict] = {}
            for membership, group in rows:
                if group is None:
                    continue
                current = counts.setdefault(
                    group.id,
                    {
                        "id": group.id,
                        "group_code": group.group_code,
                        "name": group.name,
                        "sector": group.sector,
                        "industry_family": group.industry_family,
                        "member_count": 0,
                    },
                )
                current["member_count"] += 1
            groups = sorted(
                counts.values(),
                key=lambda item: (-item["member_count"], item["name"]),
            )
            return {
                "number_of_groups": len(groups),
                "classified": sum(m.status == "classified" for m, _ in rows),
                "needs_review": sum(m.status == "needs_review" for m, _ in rows),
                "excluded": sum(m.status == "excluded" for m, _ in rows),
                "high_confidence": sum(
                    (m.classification_confidence or 0) >= 0.80
                    for m, _ in rows
                    if m.status == "classified"
                ),
                "medium_confidence": sum(
                    0.65 <= (m.classification_confidence or 0) < 0.80
                    for m, _ in rows
                    if m.status == "classified"
                ),
                "groups": groups,
            }
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc


def diagnostics(taxonomy_version: str) -> dict:
    try:
        with SessionLocal() as db:
            memberships = db.scalars(
                select(IndustryGroupMembership).where(
                    IndustryGroupMembership.assignment_version == taxonomy_version
                )
            ).all()
            instrument_ids = [row.instrument_id for row in memberships]
    except SQLAlchemyError as exc:
        raise IndustryGroupRepositoryUnavailable(str(exc)) from exc
    return universe_diagnostics(instrument_ids, taxonomy_version)


def review_queue(limit: int = 500) -> list[dict]:
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroupMembership, Instrument, IndustryGroup)
                .join(Instrument, Instrument.id == IndustryGroupMembership.instrument_id)
                .outerjoin(IndustryGroup, IndustryGroup.id == IndustryGroupMembership.industry_group_id)
                .where(IndustryGroupMembership.status == "needs_review")
                .order_by(
                    IndustryGroupMembership.classification_confidence.asc().nullsfirst(),
                    Instrument.ticker.asc(),
                )
                .limit(max(1, min(limit, 5000)))
            ).all()
            return [
                {
                    "ticker": instrument.ticker,
                    "name": instrument.name,
                    "sector": instrument.sector,
                    "industry": instrument.industry,
                    "sic": membership.sic_snapshot,
                    "suggested_group": group.name if group else "",
                    "suggested_group_id": membership.industry_group_id,
                    "confidence": membership.classification_confidence,
                    "alternative_group": (membership.explanation_json or {}).get("alternative_group", ""),
                    "explanation": membership.explanation_json,
                }
                for membership, instrument, group in rows
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
