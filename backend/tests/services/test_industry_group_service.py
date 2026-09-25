from app.repositories.industry_groups import InstrumentClassificationRow, MembershipState
from app.services import industry_groups as service


def _row(
    ticker: str,
    *,
    industry: str = "Security Software",
    instrument_type: str = "operating_company",
) -> InstrumentClassificationRow:
    return InstrumentClassificationRow(
        instrument_id=f"id-{ticker}",
        ticker=ticker,
        name=f"{ticker} Corp.",
        sector="Technology",
        industry=industry,
        exchange="NASDAQ",
        metadata_json={"instrument_type": instrument_type, "sec_sic": "7372"},
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
