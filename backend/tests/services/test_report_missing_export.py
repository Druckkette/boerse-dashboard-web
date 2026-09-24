from datetime import UTC, datetime

from app.services.report_missing_export import build_missing_rows


def _work(ticker, group, status="waiting_source", **result):
    return {"ticker": ticker, "data_group": group, "status": status,
            "result_json": result, "payload_json": {}, "error": "",
            "checked_at": datetime(2026, 9, 24, tzinfo=UTC),
            "due_at": datetime(2026, 10, 1, tzinfo=UTC)}


def test_export_names_each_missing_statement_history_and_why():
    metadata = {key: [] for key in (
        "eps_quarter_history", "annual_eps_history", "revenue_quarter_history", "annual_revenue_history"
    )}
    rows = build_missing_rows(
        [_work("TEST", "statements", reason_code="rate_limited")],
        {"TEST": {"metadata_json": metadata, "fiscal_period": "2026 Q2"}}, {},
    )
    assert len(rows) == 4
    assert {row[3] for row in rows} == {
        "EPS: Quartalsvergleiche", "EPS: Jahresvergleiche",
        "Umsatz: Quartalsvergleiche", "Umsatz: Jahresvergleiche",
    }
    assert all(row[4:6] == ("0", "3") and "begrenzt" in row[6] for row in rows)


def test_export_distinguishes_expected_filing_and_price_gates():
    history = [{"current": 2, "previous": 1} for _ in range(3)]
    metadata = {key: history for key in (
        "eps_quarter_history", "annual_eps_history", "revenue_quarter_history", "annual_revenue_history"
    )}
    rows = build_missing_rows([
        _work("FILER", "statements", reason_code="waiting_sec_data"),
        _work("NEW", "assessment"),
        _work("SHORT", "beta"),
        _work("BAD", "beta", reason_code="waiting_yahoo_data"),
        _work("READY", "assessment", status="queued"),
    ], {"FILER": {"metadata_json": metadata, "fiscal_period": "2026 Q1"},
        "SHORT": {"metadata_json": {}, "beta": None},
        "BAD": {"metadata_json": {"data_sources": {"beta": "unavailable"}}, "beta": None}},
        {"NEW": {"price_days": 42}, "SHORT": {"common_days": 80},
         "BAD": {"common_days": 250}, "READY": {"price_days": 100}})
    assert [(row[0], row[3], row[4]) for row in rows] == [
        ("FILER", "Erwartete Berichtsperiode", "2026 Q1"),
        ("NEW", "Kursdaten für Folgebewertung", "42"),
        ("SHORT", "Beta", "80"),
        ("BAD", "Beta", "250"),
    ]
    assert "Extremwert" in rows[-1][6]
