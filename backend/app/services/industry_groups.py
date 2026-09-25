from __future__ import annotations

import csv
import io
import statistics
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.data_sources.yfinance_client import fetch_company_profile
from app.domain.stocks.industry_groups import (
    TAXONOMY_VERSION,
    ClassificationFeatures,
    classification_fingerprint,
    curated_rule_match,
    exclusion_reason,
    is_eligible_operating_company,
    normalize_text,
    provider_industry_fallback,
)
from app.repositories import industry_groups as repository


PROFILE_PERSIST_BATCH_SIZE = 100
PROFILE_CIRCUIT_BREAKER_FAILURES = 12
PROFILE_RETRY_DELAYS = (
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
)


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
    excluded_because = exclusion_reason(features)
    if excluded_because:
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
                "reason": excluded_because,
            },
        }

    match = curated_rule_match(features)
    if match is not None:
        if match.rule_name.startswith("sic_"):
            source = "curated_sic_rule"
        elif match.rule_name == "canonical_provider_industry":
            source = "canonical_provider_rule"
        else:
            source = "curated_rule"
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
            "source": source,
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
                description=(
                    "Provider-industry-derived IBD-style group. "
                    "Low-frequency groups should be reviewed for canonical consolidation."
                ),
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
                "taxonomy_review_required": True,
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


def _enrich_missing_sec_sic(
    rows: list[repository.InstrumentClassificationRow],
) -> tuple[list[repository.InstrumentClassificationRow], dict]:
    """Fill missing SEC SIC data from one nightly bulk archive before using Yahoo."""
    from app.core_config import get_settings
    from app.data_sources.fundamentals_client import _sec_cik_map
    from app.data_sources.sec_submissions_cache import (
        load_submission,
        refresh_submissions_bulk_cache,
    )
    from app.services.settings import get_runtime_config_value

    stats = {
        "sec_bulk_candidates": 0,
        "sec_bulk_sic_success": 0,
        "sec_bulk_no_cik": 0,
        "sec_bulk_no_sic": 0,
        "sec_bulk_cache_available": False,
        "sec_bulk_downloaded": False,
        "sec_bulk_error": "",
    }
    candidates = []
    for row in rows:
        features = _features(row)
        if (
            is_eligible_operating_company(features)
            and not features.sic_code
            and not row.industry
            and curated_rule_match(features) is None
        ):
            candidates.append(row)
    stats["sec_bulk_candidates"] = len(candidates)
    if not candidates:
        return rows, stats

    agent = get_runtime_config_value("SEC_USER_AGENT") or get_settings().sec_user_agent
    if not agent:
        stats["sec_bulk_error"] = "SEC_USER_AGENT missing"
        return rows, stats

    try:
        cache_status = refresh_submissions_bulk_cache(agent)
        stats["sec_bulk_cache_available"] = bool(cache_status.get("available"))
        stats["sec_bulk_downloaded"] = bool(cache_status.get("downloaded"))
        if not cache_status.get("available"):
            stats["sec_bulk_error"] = str(cache_status.get("error") or "SEC submissions bulk unavailable")
            return rows, stats
        cik_map = _sec_cik_map(agent, 20)
    except Exception as exc:
        stats["sec_bulk_error"] = f"{type(exc).__name__}: {exc}"
        return rows, stats

    normalized_cik_map = {
        str(ticker).upper().replace(".", "-").replace("/", "-"): cik
        for ticker, cik in cik_map.items()
    }
    writes: list[dict] = []
    updated: dict[str, repository.InstrumentClassificationRow] = {}

    for row in candidates:
        cik = str(normalized_cik_map.get(row.ticker.upper()) or "").zfill(10)
        if not cik.isdigit() or cik == "0000000000":
            stats["sec_bulk_no_cik"] += 1
            continue
        payload = load_submission(cik)
        if not payload:
            stats["sec_bulk_no_sic"] += 1
            continue
        sic = str(payload.get("sic") or "").strip()
        sic_description = str(payload.get("sicDescription") or "").strip()
        if not sic.isdigit():
            stats["sec_bulk_no_sic"] += 1
            continue

        metadata = {
            **(row.metadata_json or {}),
            "primary_cik": cik,
            "sec_sic": sic,
            "sec_sic_description": sic_description,
            "sec_sic_cik": cik,
            "sec_sic_checked_at": datetime.now(UTC).isoformat(),
            "sec_sic_evidence": f"https://data.sec.gov/submissions/CIK{cik}.json",
            "sec_submission_bulk_source": "sec_submissions_bulk",
        }
        writes.append(
            {
                "ticker": row.ticker,
                "cik": cik,
                "sic": sic,
                "sic_description": sic_description,
            }
        )
        updated[row.ticker.upper()] = replace(row, metadata_json=metadata)
        stats["sec_bulk_sic_success"] += 1

    repository.save_sec_sic_enrichments(writes)
    if not updated:
        return rows, stats
    return [updated.get(row.ticker.upper(), row) for row in rows], stats


def _parse_iso_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _profile_retry_due(metadata: dict, now: datetime) -> bool:
    retry_at = _parse_iso_datetime(metadata.get("industry_profile_next_retry_at"))
    return retry_at is None or retry_at <= now


def _profile_retry_delay(retry_count: int, *, rate_limited: bool = False) -> timedelta:
    if rate_limited:
        return timedelta(hours=2)
    index = min(max(retry_count - 1, 0), len(PROFILE_RETRY_DELAYS) - 1)
    return PROFILE_RETRY_DELAYS[index]


def _flush_profile_writes(writes: list[dict], stats: dict) -> None:
    if not writes:
        return
    repository.save_business_profile_enrichments(writes)
    stats["profile_persist_batches"] += 1
    writes.clear()


def _enrich_missing_business_profiles(
    rows: list[repository.InstrumentClassificationRow],
) -> tuple[list[repository.InstrumentClassificationRow], dict]:
    """Enrich only unresolved operating companies and keep failures retryable.

    v1 stored a generic checked timestamp even when Yahoo returned no usable
    business profile. v2 treats those empty checks as retryable, persists
    success/failure separately and opens a circuit after repeated empty/error
    responses so one provider throttle cannot burn through the full universe.
    """
    enriched_rows: list[repository.InstrumentClassificationRow] = []
    writes: list[dict] = []
    now = datetime.now(UTC)
    consecutive_failures = 0
    circuit_open = False
    stats = {
        "external_provider_requests": 0,
        "profile_success": 0,
        "profile_empty": 0,
        "profile_errors": 0,
        "profile_rate_limited": 0,
        "profile_retry_pending": 0,
        "profile_circuit_deferred": 0,
        "profile_persist_batches": 0,
    }

    for row in rows:
        features = _features(row)
        metadata = row.metadata_json or {}
        if (
            not is_eligible_operating_company(features)
            or row.industry
            or curated_rule_match(features) is not None
        ):
            enriched_rows.append(row)
            continue

        if not _profile_retry_due(metadata, now):
            stats["profile_retry_pending"] += 1
            enriched_rows.append(row)
            continue

        if circuit_open:
            stats["profile_circuit_deferred"] += 1
            enriched_rows.append(row)
            continue

        stats["external_provider_requests"] += 1
        sector = ""
        industry = ""
        error = ""
        rate_limited = False
        try:
            profile = fetch_company_profile(row.ticker)
            sector = profile.sector
            industry = profile.industry
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            lower = error.lower()
            rate_limited = "429" in lower or "rate limit" in lower or "too many requests" in lower

        success = bool(industry)
        retry_count = int(metadata.get("industry_profile_retry_count") or 0)
        checked_at = datetime.now(UTC)

        if success:
            consecutive_failures = 0
            stats["profile_success"] += 1
            retry_count = 0
            next_retry_at = ""
        else:
            retry_count += 1
            consecutive_failures += 1
            if not error:
                error = "empty_profile"
                stats["profile_empty"] += 1
            else:
                stats["profile_errors"] += 1
            if rate_limited:
                stats["profile_rate_limited"] += 1
            next_retry_at = (checked_at + _profile_retry_delay(retry_count, rate_limited=rate_limited)).isoformat()

        write = {
            "ticker": row.ticker,
            "sector": sector,
            "industry": industry,
            "source": "yfinance",
            "error": error,
            "success": success,
            "checked_at": checked_at.isoformat(),
            "failed_at": "" if success else checked_at.isoformat(),
            "next_retry_at": next_retry_at,
            "retry_count": retry_count,
            "rate_limited": rate_limited,
        }
        writes.append(write)
        new_metadata = {
            **metadata,
            "industry_profile_checked_at": checked_at.isoformat(),
            "industry_profile_source": "yfinance",
            "industry_profile_error": error,
            "industry_profile_retry_count": retry_count,
        }
        if success:
            new_metadata["industry_profile_success_at"] = checked_at.isoformat()
            new_metadata.pop("industry_profile_failed_at", None)
            new_metadata.pop("industry_profile_next_retry_at", None)
            new_metadata.pop("industry_profile_rate_limited", None)
        else:
            new_metadata["industry_profile_failed_at"] = checked_at.isoformat()
            new_metadata["industry_profile_next_retry_at"] = next_retry_at
            new_metadata["industry_profile_rate_limited"] = rate_limited

        enriched_rows.append(
            replace(
                row,
                sector=sector or row.sector,
                industry=industry or row.industry,
                metadata_json=new_metadata,
            )
        )

        if len(writes) >= PROFILE_PERSIST_BATCH_SIZE:
            _flush_profile_writes(writes, stats)

        if rate_limited or consecutive_failures >= PROFILE_CIRCUIT_BREAKER_FAILURES:
            circuit_open = True

    _flush_profile_writes(writes, stats)
    return enriched_rows, stats


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


def _persist_results(
    rows_and_results: list[tuple[repository.InstrumentClassificationRow, ClassificationFeatures, dict]],
) -> None:
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

    rows, sec_stats = _enrich_missing_sec_sic(rows)
    rows, enrichment_stats = _enrich_missing_business_profiles(rows)
    enrichment_stats = {**sec_stats, **enrichment_stats}
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
    return _summary(rows, mode="full_rebuild", enrichment_stats=enrichment_stats)


def refresh_industry_group_memberships(universe_key: str = "us_common_stocks") -> dict:
    rows = repository.list_universe_instruments(universe_key)
    if not rows:
        raise RuntimeError(f"Universe {universe_key!r} is empty or unavailable.")

    memberships = repository.get_membership_map([row.instrument_id for row in rows])
    candidate_rows = []
    untouched_rows = []
    for row in rows:
        existing = memberships.get(row.ticker.upper())
        current_fingerprint = classification_fingerprint(_features(row))
        if existing is not None and existing.is_manual_override:
            untouched_rows.append(row)
        elif (
            existing is not None
            and existing.classification_fingerprint == current_fingerprint
            and existing.assignment_version == TAXONOMY_VERSION
            and existing.status in {"classified", "excluded"}
        ):
            untouched_rows.append(row)
        else:
            candidate_rows.append(row)

    enriched_candidates, sec_stats = _enrich_missing_sec_sic(candidate_rows)
    enriched_candidates, enrichment_stats = _enrich_missing_business_profiles(enriched_candidates)
    enrichment_stats = {**sec_stats, **enrichment_stats}
    rows_by_ticker = {row.ticker: row for row in [*untouched_rows, *enriched_candidates]}
    rows = [rows_by_ticker[row.ticker] for row in rows]
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
    result = _summary(rows, mode="incremental", enrichment_stats=enrichment_stats)
    result.update(
        {
            "existing_unchanged": existing_unchanged,
            "new": new_count,
            "reclassified_metadata_changed_or_review": reclassified,
            "manual_overrides_preserved": manual_preserved,
        }
    )
    return result


def _summary(
    rows: list[repository.InstrumentClassificationRow],
    *,
    mode: str,
    enrichment_stats: dict | None = None,
) -> dict:
    diagnostics = repository.universe_diagnostics(
        [row.instrument_id for row in rows],
        TAXONOMY_VERSION,
    )
    group_sizes = [item["member_count"] for item in diagnostics["groups"] if item["member_count"] > 0]
    smallest = sorted(
        [item for item in diagnostics["groups"] if item["member_count"] > 0],
        key=lambda item: (item["member_count"], item["name"]),
    )
    enrichment_stats = enrichment_stats or {}
    provisional_groups = [
        item for item in diagnostics["groups"]
        if str(item.get("group_code") or "").startswith("PROV_")
    ]
    quality_gates = {
        "no_provisional_groups": not provisional_groups,
        "no_needs_review": diagnostics["needs_review"] == 0,
    }
    return {
        "ok": True,
        "job_type": "rebuild_industry_groups" if mode == "full_rebuild" else "refresh_industry_group_memberships",
        "mode": mode,
        "taxonomy_version": TAXONOMY_VERSION,
        "universe_stocks": len(rows),
        "eligible_operating_companies": len(rows) - diagnostics["excluded"],
        "excluded_instruments": diagnostics["excluded"],
        "excluded_shell_companies": diagnostics.get("excluded_shell_companies", 0),
        "classified": diagnostics["classified"],
        "needs_review": diagnostics["needs_review"],
        "number_of_groups": diagnostics["number_of_groups"],
        "provisional_groups": provisional_groups,
        "quality_gates": quality_gates,
        "taxonomy_ready_for_rs": all(quality_gates.values()),
        "median_group_size": statistics.median(group_sizes) if group_sizes else 0,
        "average_group_size": (sum(group_sizes) / len(group_sizes)) if group_sizes else 0,
        "largest_groups": diagnostics["groups"][:10],
        "smallest_groups": smallest[:10],
        "small_groups_needing_review": [item for item in smallest if item["member_count"] <= 2],
        "high_confidence_assignments": diagnostics["high_confidence"],
        "medium_confidence_assignments": diagnostics["medium_confidence"],
        "classified_by_sic": diagnostics.get("classified_by_sic", 0),
        "classified_by_canonical_provider_rule": diagnostics.get("classified_by_canonical_provider_rule", 0),
        "profile_success_total": diagnostics.get("profile_success", 0),
        "profile_failed_total": diagnostics.get("profile_failed", 0),
        "profile_retry_pending_total": diagnostics.get("profile_retry_pending", 0),
        **enrichment_stats,
        "classification_sources": [
            "persisted Instrument.sector/industry",
            "persisted SEC SIC metadata",
            "persisted instrument_type",
            "deterministic curated rules",
            "canonical provider-industry mappings",
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
        "profile_error",
        "profile_retry_count",
        "profile_next_retry_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
