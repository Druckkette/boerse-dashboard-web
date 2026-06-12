from app.services import universes as universe_service


def test_yahoo_symbol_diagnostics_finds_class_share_candidate(monkeypatch) -> None:
    def fake_probe(symbol: str, *, period: str = "1mo") -> dict:
        return {
            "symbol": symbol,
            "ok": symbol == "BRK.B",
            "records_seen": 12 if symbol == "BRK.B" else 0,
            "last_date": "2026-06-12" if symbol == "BRK.B" else None,
            "error_message": "" if symbol == "BRK.B" else "Keine Daily-Bars gefunden.",
        }

    monkeypatch.setattr(universe_service, "probe_daily_price_symbol", fake_probe)

    result = universe_service.diagnose_yahoo_symbols({"tickers": ["BRK-B"], "period": "1mo"})

    assert result["ok"] is True
    assert result["job_type"] == "yahoo_symbol_diagnostics"
    assert result["candidate_found_count"] == 1
    assert result["mapped_count"] == 0
    assert result["items"][0]["source_ticker"] == "BRK-B"
    assert result["items"][0]["best_candidate"] == "BRK.B"
    assert result["items"][0]["status"] == "candidate_found"


def test_yahoo_symbol_rescue_applies_validated_mapping(monkeypatch) -> None:
    writes: list[dict] = []

    def fake_probe(symbol: str, *, period: str = "1mo") -> dict:
        return {
            "symbol": symbol,
            "ok": symbol == "BF.B",
            "records_seen": 8 if symbol == "BF.B" else 0,
            "last_date": "2026-06-12" if symbol == "BF.B" else None,
            "error_message": "",
        }

    def fake_upsert_symbol_mapping(**kwargs):
        writes.append(kwargs)

    monkeypatch.setattr(universe_service, "probe_daily_price_symbol", fake_probe)
    monkeypatch.setattr(universe_service.universe_repository, "upsert_symbol_mapping", fake_upsert_symbol_mapping)

    result = universe_service.diagnose_yahoo_symbols(
        {"tickers": ["BF-B"], "universe": "us_common_stocks"},
        apply_mappings=True,
    )

    assert result["job_type"] == "yahoo_symbol_rescue"
    assert result["mapped_count"] == 1
    assert result["items"][0]["mapping_applied"] is True
    assert writes == [
        {
            "key": "us_common_stocks",
            "source_ticker": "BF-B",
            "yahoo_symbol": "BF.B",
            "status": "active",
            "source": "auto_rescue",
            "note": "Automatisch validiert über yfinance-Daily-Probe.",
            "confidence": 0.80,
        }
    ]


def test_yahoo_symbol_diagnostics_uses_latest_failed_price_tickers(monkeypatch) -> None:
    class Job:
        job_type = "refresh_prices"
        result = {"failed_tickers": ["bad-a", "bad-a", "bad-b"]}

    seen: list[str] = []

    def fake_probe(symbol: str, *, period: str = "1mo") -> dict:
        seen.append(symbol)
        return {"symbol": symbol, "ok": False, "records_seen": 0, "error_message": "missing"}

    monkeypatch.setattr(universe_service.job_repository, "list_jobs", lambda limit=25: [Job()])
    monkeypatch.setattr(universe_service, "probe_daily_price_symbol", fake_probe)

    result = universe_service.diagnose_yahoo_symbols({"limit": 5})

    assert result["requested_count"] == 2
    assert seen == ["BAD-A", "BAD.A", "BADA", "BAD-B", "BAD.B", "BADB"]
