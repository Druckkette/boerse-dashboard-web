from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.repositories.industry_groups import InstrumentClassificationRow, MembershipState
from app.services import industry_groups as service


def _row(
    ticker: str,
    *,
    industry: str = "Security Software",
    instrument_type: str = "operating_company",
    sic: str = "7372",
    metadata: dict | None = None,
) -> InstrumentClassificationRow:
    saved = {"instrument_type": instrument_type}
    if sic:
        saved["sec_sic"] = sic
    if metadata:
        saved.update(metadata)
    return InstrumentClassificationRow(
        instrument_id=f"id-{ticker}",
        ticker=ticker,
        name=f"{ticker} Corp.",
        sector="Technology" if industry else "",
        industry=industry,
        exchange="NASDAQ",
        metadata_json=saved,
    )


def _diagnostics(rows):
    return {
        "number_of_groups": 1,
        "classified": len(rows),
        "needs_review": 0,
        "excluded": 0,
        "high_confidence": len(rows),
        "medium_confidence": 0,
        "groups": [
            {
                "id": "g1",
                "group_code": "SOFTSEC",
                "name": "Software – Security",
                "sector": "Technology",
                "industry_family": "Software",
                "member_count": len(rows),
            }
        ],
    }


def test_incremental_skips_unchanged_membership(monkeypatch):
    row = _row("PANW")
    fp = service.classification_fingerprint(service._features(row))
    monkeypatch.setattr(service.repository, "list_universe_instruments", lambda key: [row])
    monkeypatch.setattr(
        service.repository,
        "get_membership_map",
        lambda ids: {
            "PANW": MembershipState(
                instrument_id=row.instrument_id,
                ticker="PANW",
                status="classified",
                classification_fingerprint=fp,
                assignment_version=service.TAXONOMY_VERSION,
                is_manual_override=False,
            )
        },
    )
    monkeypatch.setattr(service.repository, "load_exact_industry_rule_map", lambda version: {})
    writes = []
    monkeypatch.setattr(
        service.repository,
        "persist_classification_batch",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        service.repository,
        "universe_diagnostics",
        lambda ids, version: _diagnostics([row]),
    )

    result = service.refresh_industry_group_memberships()

    assert result["existing_unchanged"] == 1
    assert result["new"] == 0
    assert result["reclassified_metadata_changed_or_review"] == 0
    assert writes and writes[0]["memberships"] == []


def test_incremental_classifies_only_new_stock(monkeypatch):
    old = _row("PANW")
    new = _row("CRWD")
    old_fp = service.classification_fingerprint(service._features(old))
    monkeypatch.setattr(service.repository, "list_universe_instruments", lambda key: [old, new])
    monkeypatch.setattr(
        service.repository,
        "get_membership_map",
        lambda ids: {
            "PANW": MembershipState(
                instrument_id=old.instrument_id,
                ticker="PANW",
                status="classified",
                classification_fingerprint=old_fp,
                assignment_version=service.TAXONOMY_VERSION,
                is_manual_override=False,
            )
        },
    )
    monkeypatch.setattr(service.repository, "load_exact_industry_rule_map", lambda version: {})
    writes = []
    monkeypatch.setattr(
        service.repository,
        "persist_classification_batch",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        service.repository,
        "universe_diagnostics",
        lambda ids, version: _diagnostics([old, new]),
    )

    result = service.refresh_industry_group_memberships()

    assert result["existing_unchanged"] == 1
    assert result["new"] == 1
    assert len(writes[0]["memberships"]) == 1
    assert writes[0]["memberships"][0]["ticker"] == "CRWD"


def test_changed_fingerprint_triggers_targeted_reclassification(monkeypatch):
    row = _row("PANW", industry="Security Software")
    monkeypatch.setattr(service.repository, "list_universe_instruments", lambda key: [row])
    monkeypatch.setattr(
        service.repository,
        "get_membership_map",
        lambda ids: {
            "PANW": MembershipState(
                instrument_id=row.instrument_id,
                ticker="PANW",
                status="classified",
                classification_fingerprint="old-fingerprint",
                assignment_version=service.TAXONOMY_VERSION,
                is_manual_override=False,
            )
        },
    )
    monkeypatch.setattr(service.repository, "load_exact_industry_rule_map", lambda version: {})
    writes = []
    monkeypatch.setattr(
        service.repository,
        "persist_classification_batch",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        service.repository,
        "universe_diagnostics",
        lambda ids, version: _diagnostics([row]),
    )

    result = service.refresh_industry_group_memberships()

    assert result["reclassified_metadata_changed_or_review"] == 1
    assert writes[0]["memberships"][0]["classification_fingerprint"] != "old-fingerprint"


def test_manual_override_is_never_reprocessed(monkeypatch):
    row = _row("TSLA", industry="Auto Manufacturers")
    monkeypatch.setattr(service.repository, "list_universe_instruments", lambda key: [row])
    monkeypatch.setattr(
        service.repository,
        "get_membership_map",
        lambda ids: {
            "TSLA": MembershipState(
                instrument_id=row.instrument_id,
                ticker="TSLA",
                status="classified",
                classification_fingerprint="manual",
                assignment_version=service.TAXONOMY_VERSION,
                is_manual_override=True,
            )
        },
    )
    monkeypatch.setattr(service.repository, "load_exact_industry_rule_map", lambda version: {})
    writes = []
    monkeypatch.setattr(
        service.repository,
        "persist_classification_batch",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        service.repository,
        "universe_diagnostics",
        lambda ids, version: _diagnostics([row]),
    )

    result = service.refresh_industry_group_memberships()

    assert result["manual_overrides_preserved"] == 1
    assert writes[0]["memberships"] == []


def test_full_rebuild_batches_all_writes_once(monkeypatch):
    rows = [_row("PANW"), _row("CRWD")]
    monkeypatch.setattr(service.repository, "list_universe_instruments", lambda key: rows)
    monkeypatch.setattr(service.repository, "load_exact_industry_rule_map", lambda version: {})
    writes = []
    monkeypatch.setattr(
        service.repository,
        "persist_classification_batch",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        service.repository,
        "universe_diagnostics",
        lambda ids, version: _diagnostics(rows),
    )

    result = service.rebuild_industry_groups()

    assert result["mode"] == "full_rebuild"
    assert len(writes) == 1
    assert len(writes[0]["memberships"]) == 2
    assert "SOFTSEC" in writes[0]["group_definitions"]


def test_v1_empty_profile_check_is_retryable_and_success_is_persisted(monkeypatch):
    row = _row(
        "MSFT",
        industry="",
        sic="",
        metadata={"industry_profile_checked_at": "2026-09-25T12:00:00+00:00"},
    )
    writes = []
    monkeypatch.setattr(
        service,
        "fetch_company_profile",
        lambda ticker: SimpleNamespace(
            ticker=ticker,
            sector="Technology",
            industry="Software - Infrastructure",
        ),
    )
    monkeypatch.setattr(
        service.repository,
        "save_business_profile_enrichments",
        lambda items: writes.extend(items),
    )

    enriched, stats = service._enrich_missing_business_profiles([row])

    assert stats["external_provider_requests"] == 1
    assert stats["profile_success"] == 1
    assert enriched[0].industry == "Software - Infrastructure"
    assert writes[0]["success"] is True
    assert writes[0]["retry_count"] == 0


def test_profile_retry_window_prevents_immediate_refetch(monkeypatch):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    row = _row(
        "UNKNOWN",
        industry="",
        sic="",
        metadata={"industry_profile_next_retry_at": future},
    )
    called = []
    monkeypatch.setattr(
        service,
        "fetch_company_profile",
        lambda ticker: called.append(ticker),
    )
    monkeypatch.setattr(
        service.repository,
        "save_business_profile_enrichments",
        lambda items: None,
    )

    enriched, stats = service._enrich_missing_business_profiles([row])

    assert called == []
    assert enriched[0].industry == ""
    assert stats["profile_retry_pending"] == 1


def test_profile_circuit_breaker_stops_after_consecutive_empty_profiles(monkeypatch):
    rows = [_row(f"X{i:02d}", industry="", sic="") for i in range(15)]
    calls = []
    writes = []
    monkeypatch.setattr(
        service,
        "fetch_company_profile",
        lambda ticker: (
            calls.append(ticker)
            or SimpleNamespace(ticker=ticker, sector="", industry="")
        ),
    )
    monkeypatch.setattr(
        service.repository,
        "save_business_profile_enrichments",
        lambda items: writes.extend(items),
    )

    _enriched, stats = service._enrich_missing_business_profiles(rows)

    assert len(calls) == service.PROFILE_CIRCUIT_BREAKER_FAILURES
    assert stats["profile_empty"] == service.PROFILE_CIRCUIT_BREAKER_FAILURES
    assert stats["profile_circuit_deferred"] == 3
    assert all(item["success"] is False for item in writes)


def test_sec_bulk_sic_enrichment_precedes_yahoo(monkeypatch):
    from app.data_sources import fundamentals_client, sec_submissions_cache
    from app.services import settings as settings_service

    row = _row("MSFT", industry="", sic="")
    writes = []
    monkeypatch.setattr(settings_service, "get_runtime_config_value", lambda key: "test test@example.com")
    monkeypatch.setattr(
        sec_submissions_cache,
        "refresh_submissions_bulk_cache",
        lambda agent: {"available": True, "downloaded": False},
    )
    monkeypatch.setattr(
        fundamentals_client,
        "_sec_cik_map",
        lambda agent, timeout: {"MSFT": "789019"},
    )
    monkeypatch.setattr(
        sec_submissions_cache,
        "load_submission",
        lambda cik: {"sic": "7372", "sicDescription": "Services-Prepackaged Software"},
    )
    monkeypatch.setattr(
        service.repository,
        "save_sec_sic_enrichments",
        lambda items: writes.extend(items),
    )

    enriched, stats = service._enrich_missing_sec_sic([row])

    assert stats["sec_bulk_candidates"] == 1
    assert stats["sec_bulk_sic_success"] == 1
    assert enriched[0].metadata_json["sec_sic"] == "7372"
    assert enriched[0].metadata_json["primary_cik"] == "0000789019"
    assert writes == [
        {
            "ticker": "MSFT",
            "cik": "0000789019",
            "sic": "7372",
            "sic_description": "Services-Prepackaged Software",
        }
    ]
    match = service.curated_rule_match(service._features(enriched[0]))
    assert match is not None
    assert match.group_code == "SOFTAPP"
