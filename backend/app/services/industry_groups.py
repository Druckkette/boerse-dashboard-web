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


def _group_definition(*, code: str, name: str, sector: str, family: str, description: str) -> dict:
    return {
        "group_code": code,
        "name": name,
        "sector": sector,
        "industry_family": family,
        "description": description,
    }


def _classify_one(
    features: ClassificationFeatures,
    *,
    exact_rules: dict[str, dict],
) -> dict:
    fingerprint = classification_fingerprint(features)
    if not is_eligible_operating_company(features):
        return {
            "group_code": "",
            "group_definition": None,
            "status": "excluded",
            "source": "instrument_type",
            "confidence": 1.0,
            "fingerprint": fingerprint,
            "normalized_industry": "",
            "create_exact_rule": False,
            "explanation": {
                "instrument_type": features.instrument_type,
                "reason": "non_operating_security",
            },
        }

    match = curated_rule_match(features)
    if match is not None:
        return {
            "group_code": match.group_code,
            "group_definition": _group_definition(
                code=match.group_code,
                name=match.group_name,
                sector=match.sector,
                family=match.family,
                description="Deterministic IBD-style business classification; not a proprietary IBD label.",
            ),
            "status": "classified",
            "source": "curated_rule",
            "confidence": match.confidence,
            "fingerprint": fingerprint,
            "normalized_industry": normalize_text(features.industry),
            "create_exact_rule": False,
            "explanation": {
                "matched_rule": match.rule_name,
                "industry": features.industry,
                "sic": features.sic_code,
                "sic_description": features.sic_description,
                "confidence": match.confidence,
            },
        }

    normalized_industry = normalize_text(features.industry)
    exact = exact_rules.get(normalized_industry) if normalized_industry else None
    if exact is not None:
        return {
            "group_code": str(exact["group_code"]),
            "group_definition": _group_definition(
                code=str(exact["group_code"]),
                name=str(exact["group_name"]),
                sector=str(exact["sector"]),
                family=str(exact["industry_family"]),
                description="Persisted deterministic provider-industry mapping.",
            ),
            "status": "classified",
            "source": "persisted_exact_industry_rule",
            "confidence": float(exact["confidence"]),
            "fingerprint": fingerprint,
            "normalized_industry": normalized_industry,
            "create_exact_rule": False,
            "explanation": {
                "matched_rule": "provider_industry_exact",
                "normalized_industry": normalized_industry,
                "industry": features.industry,
                "target_group": exact["group_name"],
                "confidence": float(exact["confidence"]),
            },
        }

    fallback = provider_industry_fallback(features)
    if fallback is not None:
        return {
            "group_code": fallback.group_code,
            "group_definition": _group_definition(
                code=fallback.group_code,
                name=fallback.group_name,
                sector=fallback.sector,
                family=fallback.family,
                description="Provider-industry-derived IBD-style group created during taxonomy bootstrap.",
            ),
            "status": "classified",
            "source": "provider_industry_exact",
            "confidence": fallback.confidence,
            "fingerprint": fingerprint,
            "normalized_industry": normalized_industry,
            "create_exact_rule": True,
            "explanation": {
                "matched_rule": fallback.rule_name,
                "normalized_industry": normalized_industry,
                "industry": features.industry,
                "confidence": fallback.confidence,
            },
        }

    return {
        "group_code": "",
        "group_definition": None,
        "status": "needs_review",
        "source": "insufficient_metadata",
        "confidence": 0.0,
        "fingerprint": fingerprint,
        "normalized_industry": "",
        "create_exact_rule": False,
        "explanation": {
            "reason": "No usable persisted industry and no deterministic curated rule matched.",
            "sector": features.sector,
            "industry": features.industry,
            "sic": features.sic_code,
            "sic_description": features.sic_description,
        },
    }


def _membership_write(
    row: repository.InstrumentClassificationRow,
    features: ClassificationFeatures,
    result: dict,
) -> dict:
    return {
        "instrument_id": row.instrument_id,
        "ticker": row.ticker,
        "group_code": result["group_code"],
        "status": result["status"],
        "classification_source": result["source"],
        "classification_confidence": result["confidence"],
        "classification_fingerprint": result["fingerprint"],
        "sector_snapshot": features.sector,
        "industry_snapshot": features.industry,
        "sic_snapshot": features.sic_code,
        "explanation_json": result["explanation"],
    }


def _persist_results(rows_and_results: list[tuple[repository.InstrumentClassificationRow, ClassificationFeatures, dict]]) -> None:
    group_definitions: dict[str, dict] = {}
    exact_rules: dict[str, dict] = {}
    memberships: list[dict] = []

    for row, features, result in rows_and_results:
        definition = result.get("group_definition")
        if definition:
            group_definitions[str(result["group_code"])] = definition
        if result.get("create_exact_rule") and result.get("normalized_industry"):
            exact_rules[str(result["normalized_industry"])] = {
                "group_code": result["group_code"],
                "confidence": result["confidence"],
            }
        memberships.append(_membership_write(row, features, result))

    repository.persist_classification_batch(
        taxonomy_version=TAXONOMY_VERSION,
        group_definitions=group_definitions,
        exact_industry_rules=exact_rules,
        memberships=memberships,
    )


def rebuild_industry_groups(universe_key: str = "us_common_stocks") -> dict:
    rows = repository.list_universe_instruments(universe_key)
    if not rows:
        raise RuntimeError(f"Universe {universe_key!r} is empty or unavailable.")

    exact_rules = repository.load_exact_industry_rule_map(TAXONOMY_VERSION)
    classified_rows: list[tuple[repository.InstrumentClassificationRow, ClassificationFeatures, dict]] = []
    for row in rows:
        features = _features(row)
        result = _classify_one(features, exact_rules=exact_rules)
        classified_rows.append((row, features, result))
        if result.get("create_exact_rule") and result.get("normalized_industry"):
            exact_rules[str(result["normalized_industry"])] = {
                "group_code": result["group_code"],
                "group_name": result["group_definition"]["name"],
                "sector": result["group_definition"]["sector"],
                "industry_family": result["group_definition"]["industry_family"],
                "confidence": result["confidence"],
            }

    _persist_results(classified_rows)
    return _summary(rows, mode="full_rebuild")


def refresh_industry_group_memberships(universe_key: str = "us_common_stocks") -> dict:
    rows = repository.list_universe_instruments(universe_key)
    if not rows:
        raise RuntimeError(f"Universe {universe_key!r} is empty or unavailable.")

    memberships = repository.get_membership_map([row.instrument_id for row in rows])
    exact_rules = repository.load_exact_industry_rule_map(TAXONOMY_VERSION)
    changed_rows: list[tuple[repository.InstrumentClassificationRow, ClassificationFeatures, dict]] = []
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

        result = _classify_one(features, exact_rules=exact_rules)
        changed_rows.append((row, features, result))
        if result.get("create_exact_rule") and result.get("normalized_industry"):
            exact_rules[str(result["normalized_industry"])] = {
                "group_code": result["group_code"],
                "group_name": result["group_definition"]["name"],
                "sector": result["group_definition"]["sector"],
                "industry_family": result["group_definition"]["industry_family"],
                "confidence": result["confidence"],
            }
        if existing is None:
            new_count += 1
        else:
            reclassified += 1

    _persist_results(changed_rows)
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
    diagnostics = repository.universe_diagnostics(
        [row.instrument_id for row in rows],
        TAXONOMY_VERSION,
    )
    group_sizes = [item["member_count"] for item in diagnostics["groups"] if item["member_count"] > 0]
    smallest = sorted(
        [item for item in diagnostics["groups"] if item["member_count"] > 0],
        key=lambda item: (item["member_count"], item["name"]),
    )
    return {
        "ok": True,
        "job_type": "rebuild_industry_groups" if mode == "full_rebuild" else "refresh_industry_group_memberships",
        "mode": mode,
        "taxonomy_version": TAXONOMY_VERSION,
        "universe_stocks": len(rows),
        "eligible_operating_companies": len(rows) - diagnostics["excluded"],
        "excluded_instruments": diagnostics["excluded"],
        "classified": diagnostics["classified"],
        "needs_review": diagnostics["needs_review"],
        "number_of_groups": diagnostics["number_of_groups"],
        "median_group_size": statistics.median(group_sizes) if group_sizes else 0,
        "average_group_size": (sum(group_sizes) / len(group_sizes)) if group_sizes else 0,
        "largest_groups": diagnostics["groups"][:10],
        "smallest_groups": smallest[:10],
        "small_groups_needing_review": [item for item in smallest if item["member_count"] <= 2],
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
        "ticker",
        "name",
        "sector",
        "original_industry",
        "sic",
        "sic_description",
        "industry_group",
        "industry_family",
        "confidence",
        "classification_source",
        "assignment_version",
        "manual_override",
        "status",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
