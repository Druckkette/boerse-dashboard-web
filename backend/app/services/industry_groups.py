from __future__ import annotations

import csv
import io
import statistics
from datetime import UTC, datetime

from app.domain.stocks.industry_groups import (
    TAXONOMY_VERSION,
    ClassificationFeatures,
    classification_fingerprint,
    curated_rule_match,
    is_eligible_operating_company,
    normalize_text,
    provider_industry_fallback,
)
from app.repositories import industry_groups as repository


def _features(row: repository.InstrumentClassificationRow) -> ClassificationFeatures:
    metadata = row.metadata_json or {}
    return ClassificationFeatures(
        ticker=row.ticker,
        company_name=row.name,
        sector=row.sector,
        industry=row.industry,
        sic_code=str(metadata.get("sec_sic") or ""),
        sic_description=str(metadata.get("sec_sic_description") or ""),
        instrument_type=str(metadata.get("instrument_type") or "unknown"),
        exchange=row.exchange,
    )


def _classify_one(
    row: repository.InstrumentClassificationRow,
    *,
    create_provider_rule: bool,
) -> dict:
    features = _features(row)
    fingerprint = classification_fingerprint(features)
    if not is_eligible_operating_company(features):
        return {
            "group_id": None,
            "status": "excluded",
            "source": "instrument_type",
            "confidence": 1.0,
            "fingerprint": fingerprint,
            "explanation": {
                "instrument_type": features.instrument_type,
                "reason": "non_operating_security",
            },
        }

    match = curated_rule_match(features)
    if match is not None:
        group_id = repository.get_or_create_group(
            group_code=match.group_code,
            name=match.group_name,
            sector=match.sector,
            industry_family=match.family,
            taxonomy_version=TAXONOMY_VERSION,
            description="Deterministic IBD-style business classification; not a proprietary IBD label.",
        )
        return {
            "group_id": group_id,
            "status": "classified",
            "source": "curated_rule",
            "confidence": match.confidence,
            "fingerprint": fingerprint,
            "explanation": {
                "matched_rule": match.rule_name,
                "industry": features.industry,
                "sic": features.sic_code,
                "sic_description": features.sic_description,
                "confidence": match.confidence,
            },
        }

    normalized_industry = normalize_text(features.industry)
    exact = repository.exact_industry_rule(normalized_industry, TAXONOMY_VERSION)
    if exact is not None:
        group = repository.group_by_id(exact[0])
        return {
            "group_id": exact[0],
            "status": "classified",
            "source": "persisted_exact_industry_rule",
            "confidence": exact[1],
            "fingerprint": fingerprint,
            "explanation": {
                "matched_rule": "provider_industry_exact",
                "normalized_industry": normalized_industry,
                "industry": features.industry,
                "target_group": group.name if group else "",
                "confidence": exact[1],
            },
        }

    fallback = provider_industry_fallback(features)
    if fallback is not None:
        group_id = repository.get_or_create_group(
            group_code=fallback.group_code,
            name=fallback.group_name,
            sector=fallback.sector,
            industry_family=fallback.family,
            taxonomy_version=TAXONOMY_VERSION,
            description="Provider-industry-derived IBD-style group created during taxonomy bootstrap.",
        )
        if create_provider_rule:
            repository.upsert_exact_industry_rule(
                normalized_industry=normalized_industry,
                group_id=group_id,
                confidence=fallback.confidence,
                taxonomy_version=TAXONOMY_VERSION,
            )
        return {
            "group_id": group_id,
            "status": "classified",
            "source": "provider_industry_exact",
            "confidence": fallback.confidence,
            "fingerprint": fingerprint,
            "explanation": {
                "matched_rule": fallback.rule_name,
                "normalized_industry": normalized_industry,
                "industry": features.industry,
                "confidence": fallback.confidence,
            },
        }

    return {
        "group_id": None,
        "status": "needs_review",
        "source": "insufficient_metadata",
        "confidence": 0.0,
        "fingerprint": fingerprint,
        "explanation": {
            "reason": "No usable persisted industry and no deterministic curated rule matched.",
            "sector": features.sector,
            "industry": features.industry,
            "sic": features.sic_code,
            "sic_description": features.sic_description,
        },
    }


def rebuild_industry_groups(universe_key: str = "us_common_stocks") -> dict:
    rows = repository.list_universe_instruments(universe_key)
    if not rows:
        raise RuntimeError(f"Universe {universe_key!r} is empty or unavailable.")

    for row in rows:
        features = _features(row)
        result = _classify_one(row, create_provider_rule=True)
        repository.upsert_membership(
            instrument_id=row.instrument_id,
            ticker=row.ticker,
            industry_group_id=result["group_id"],
            status=result["status"],
            classification_source=result["source"],
            classification_confidence=result["confidence"],
            classification_fingerprint=result["fingerprint"],
            sector_snapshot=features.sector,
            industry_snapshot=features.industry,
            sic_snapshot=features.sic_code,
            assignment_version=TAXONOMY_VERSION,
            explanation_json=result["explanation"],
        )

    return _summary(rows, mode="full_rebuild")


def refresh_industry_group_memberships(universe_key: str = "us_common_stocks") -> dict:
    rows = repository.list_universe_instruments(universe_key)
    memberships = repository.get_membership_map()
    existing_unchanged = new_count = reclassified = manual_preserved = 0

    for row in rows:
        features = _features(row)
        fingerprint = classification_fingerprint(features)
        existing = memberships.get(row.ticker.upper())
        if existing is not None and existing.is_manual_override:
            manual_preserved += 1
            continue
        if (
            existing is not None
            and existing.classification_fingerprint == fingerprint
            and existing.assignment_version == TAXONOMY_VERSION
            and existing.status in {"classified", "excluded"}
        ):
            existing_unchanged += 1
            continue

        result = _classify_one(row, create_provider_rule=True)
        repository.upsert_membership(
            instrument_id=row.instrument_id,
            ticker=row.ticker,
            industry_group_id=result["group_id"],
            status=result["status"],
            classification_source=result["source"],
            classification_confidence=result["confidence"],
            classification_fingerprint=result["fingerprint"],
            sector_snapshot=features.sector,
            industry_snapshot=features.industry,
            sic_snapshot=features.sic_code,
            assignment_version=TAXONOMY_VERSION,
            explanation_json=result["explanation"],
        )
        if existing is None:
            new_count += 1
        else:
            reclassified += 1

    result = _summary(rows, mode="incremental")
    result.update(
        {
            "existing_unchanged": existing_unchanged,
            "new": new_count,
            "reclassified_metadata_changed_or_review": reclassified,
            "manual_overrides_preserved": manual_preserved,
        }
    )
    return result


def _summary(rows: list[repository.InstrumentClassificationRow], *, mode: str) -> dict:
    diagnostics = repository.diagnostics(TAXONOMY_VERSION)
    group_sizes = [item["member_count"] for item in diagnostics["groups"] if item["member_count"] > 0]
    eligible = len(rows) - diagnostics["excluded"]
    return {
        "ok": True,
        "job_type": "rebuild_industry_groups" if mode == "full_rebuild" else "refresh_industry_group_memberships",
        "mode": mode,
        "taxonomy_version": TAXONOMY_VERSION,
        "universe_stocks": len(rows),
        "eligible_operating_companies": eligible,
        "excluded_instruments": diagnostics["excluded"],
        "classified": diagnostics["classified"],
        "needs_review": diagnostics["needs_review"],
        "number_of_groups": diagnostics["number_of_groups"],
        "median_group_size": statistics.median(group_sizes) if group_sizes else 0,
        "average_group_size": (sum(group_sizes) / len(group_sizes)) if group_sizes else 0,
        "largest_groups": diagnostics["groups"][:10],
        "smallest_groups": sorted(
            [item for item in diagnostics["groups"] if item["member_count"] > 0],
            key=lambda item: (item["member_count"], item["name"]),
        )[:10],
        "high_confidence_assignments": diagnostics["high_confidence"],
        "medium_confidence_assignments": diagnostics["medium_confidence"],
        "external_provider_requests": 0,
        "classification_sources": [
            "persisted Instrument.sector/industry",
            "persisted SEC SIC metadata",
            "persisted instrument_type",
            "deterministic curated rules",
            "persisted exact provider-industry mappings",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def review_queue(limit: int = 500) -> list[dict]:
    return repository.review_queue(limit=limit)


def set_manual_override(*, ticker: str, group_id: str, reason: str) -> None:
    repository.set_manual_override(
        ticker=ticker,
        group_id=group_id,
        reason=reason,
        taxonomy_version=TAXONOMY_VERSION,
    )


def audit_csv() -> str:
    rows = repository.membership_export_rows(TAXONOMY_VERSION)
    buffer = io.StringIO()
    fieldnames = [
        "ticker", "name", "sector", "original_industry", "sic", "sic_description",
        "industry_group", "industry_family", "confidence", "classification_source",
        "assignment_version", "manual_override", "status",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
