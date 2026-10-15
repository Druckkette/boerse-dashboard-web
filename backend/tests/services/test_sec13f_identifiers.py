from app.research.repair_sec13f_identifiers import valid_cusip


def test_only_checksum_valid_cusips_can_create_a_security_mapping():
    assert valid_cusip("037833100")
    assert valid_cusip("H5919C104")
    assert not valid_cusip("037833101")
    assert not valid_cusip("ONON")
    assert not valid_cusip("")


def test_cached_identities_do_not_spend_provider_quota(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from app.research import repair_sec13f_identifiers as module
    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def scalars(self, query):
            return [SimpleNamespace(ticker="VEEV", metadata_json={"sec13f_identity": {
                "symbol": "VEEV", "cusip": "922475108", "checked_at": datetime.now(UTC).isoformat()}})]
    monkeypatch.setattr(module, "SessionLocal", FakeSession)
    monkeypatch.setattr(module, "get_runtime_config_value", lambda key: "test-only-key")
    monkeypatch.setattr(module, "guarded_fmp_get", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Cached profile fetched again")))
    monkeypatch.setattr(module.jobs, "create_job", lambda *a, **kw: SimpleNamespace(job_id="fixture"))
    monkeypatch.setattr(module.jobs, "mark_running", lambda *a, **kw: None)
    monkeypatch.setattr(module.jobs, "mark_done", lambda *a, **kw: None)
    result = module.repair(["VEEV"], workers=1)
    assert result["counts"] == {"cached": 1}


def test_provider_limit_defers_remaining_identifiers(monkeypatch):
    from types import SimpleNamespace
    from app.research import repair_sec13f_identifiers as module
    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def scalars(self, query): return []
    calls = []
    def limited(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(status_code=429)
    monkeypatch.setattr(module, "SessionLocal", FakeSession)
    monkeypatch.setattr(module, "get_runtime_config_value", lambda key: "test-only-key")
    monkeypatch.setattr(module, "guarded_fmp_get", limited)
    monkeypatch.setattr(module.jobs, "create_job", lambda *a, **kw: SimpleNamespace(job_id="fixture"))
    monkeypatch.setattr(module.jobs, "mark_running", lambda *a, **kw: None)
    monkeypatch.setattr(module.jobs, "mark_done", lambda *a, **kw: None)
    result = module.repair(["ONE", "TWO", "THREE"], workers=1)
    assert len(calls) == 1
    assert result["status"] == "partial"
    assert result["counts"] == {"deferred": 2, "provider_blocked": 1}
