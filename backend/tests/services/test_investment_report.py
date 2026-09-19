from datetime import UTC, datetime
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from app.main import app
from app.reports.model import InvestmentReport, ReportSection
from app.reports.pdf import fields, render_report


def report(**kwargs):
    return InvestmentReport(ticker="TEST", name="Test AG & Co. <Investment>",
                            exported_at=datetime(2026, 9, 19, 12, tzinfo=UTC), **kwargs)


def test_multipage_complete_a4_and_reproducible():
    checks = [{"category": "technical", "label": f"Kriterium {i}", "passed": i % 2 == 0,
               "detail": "Prüfung & Begründung <kein HTML>. " * 12} for i in range(100)]
    data = report(assessment={"source": "database", "scores": {"overall": 0}, "checks": checks},
                  sections=[ReportSection("Notizen", {"Begründung": "Langtext " * 2200 + " SCHLUSSMARKE"})])
    pdf = render_report(data)
    assert pdf == render_report(data)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) > 5
    text = "\n".join(page.extract_text() for page in reader.pages)
    for i in range(100):
        assert f"Kriterium {i}" in text
    assert "SCHLUSSMARKE" in text
    assert "0 / 100" in text
    for number, page in enumerate(reader.pages, 1):
        assert abs(float(page.mediabox.width) - 595.276) < .01
        assert abs(float(page.mediabox.height) - 841.89) < .01
        assert f"Seite {number}" in page.extract_text()
        assert "INVESTMENT REPORT" in page.extract_text()


def test_missing_does_not_export_placeholder_scores_or_markup():
    data = report(assessment={"source": "missing", "scores": {"overall": 0}},
                  journal=[{"basis_text": '<img src="file:///secret"/> & Begründung',
                            "chart_images": {"daily_chart": "https://example.com/chart.png"}}])
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(render_report(data))).pages)
    assert "0 / 100" not in text
    assert "Keine Bewertung gespeichert" in text
    assert "gespeichertes Bild nicht darstellbar" in text
    assert '<img src="file:///secret"/>' in text
    assert list(fields({"zero": 0, "false": False, "unknown": None})) == [
        ("Zero", "0"), ("False", "Nein"), ("Unknown", "Nicht vorhanden")]


def test_export_route_headers_and_trade_id(monkeypatch):
    from app.reports import collect
    calls = []
    monkeypatch.setattr(collect, "collect_report", lambda ticker, trade_id: (
        calls.append((ticker, trade_id)) or report(trade_id=trade_id)))
    response = TestClient(app).get("/api/v1/stocks/TEST/report.pdf?trade_id=entry-1")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert "TEST-Trade-Report.pdf" in response.headers["content-disposition"]
    assert calls == [("TEST", "entry-1")]


@pytest.mark.parametrize("error,status", [(LookupError("Nicht gefunden"), 404), (RuntimeError("secret"), 500)])
def test_export_errors_do_not_leak_internals(monkeypatch, error, status):
    from app.reports import collect
    def fail(*args):
        raise error
    monkeypatch.setattr(collect, "collect_report", fail)
    response = TestClient(app).get("/api/v1/stocks/TEST/report.pdf")
    assert response.status_code == status
    assert "secret" not in response.text


def test_invalid_ticker():
    assert TestClient(app).get("/api/v1/stocks/TEST%22/report.pdf").status_code == 422


def test_sell_preview_is_read_only(monkeypatch):
    from app.domain.sell import service
    calls = []
    monkeypatch.setattr(service, "_evaluate_position_sell_decision", lambda *args, **kwargs: calls.append(kwargs))
    service.preview_position_sell_decision("TEST")
    assert calls == [{"persist_state": False}]


def test_position_currency_conversion_and_missing_prices(monkeypatch):
    from app.reports import collect
    from app.repositories.portfolio import PortfolioPositionRow
    row = PortfolioPositionRow(ticker="TEST", name="Test", shares=10, entry_price=80,
                               current_price=110, currency="EUR", buy_date=None,
                               current_price_source="price_cache", stop_price=75)
    monkeypatch.setattr(collect, "cached_currency_usd_factor", lambda c: {"USD": 1, "EUR": 1.1}[c])
    data, buy_row = collect.position_data(row, "USD")
    assert data["current_price"] == pytest.approx(100)
    assert data["market_value"] == pytest.approx(1000)
    assert data["pnl_abs"] == pytest.approx(200)
    assert data["position_loss_risk"] == pytest.approx(250)
    assert buy_row.entry_price == pytest.approx(88)
    monkeypatch.setattr(collect, "cached_currency_usd_factor", lambda c: None)
    data, buy_row = collect.position_data(row, "USD")
    assert data["current_price"] is None
    assert data["pnl_abs"] is None
    assert buy_row is None
    from dataclasses import replace
    data, _ = collect.position_data(replace(row, current_price_source="position_entry"), "EUR")
    assert data["current_price"] is None
    assert data["invested_amount"] == 800


def test_historical_report_never_calls_current_assessments(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from app.reports import collect
    entry = {"id": "entry-1", "ticker": "TEST", "portfolio_snapshot": {}, "market_snapshot": {},
             "stock_snapshot": {"assessment": {"source": "database", "scores": {"overall": 42}}}}
    selected = SimpleNamespace(id="entry-1", linked_entry_id=None, ticker="TEST")
    queries = []
    class DB:
        def scalar(self, query):
            return None
        def get(self, model, identity):
            return selected
        def scalars(self, query):
            queries.append(str(query))
            return [selected]
    monkeypatch.setattr(collect, "SessionLocal", lambda: nullcontext(DB()))
    monkeypatch.setattr(collect, "_detail_from_row", lambda row: SimpleNamespace(model_dump=lambda **kwargs: entry))
    def forbidden(*args, **kwargs):
        raise AssertionError("Historical export called live data")
    monkeypatch.setattr(collect, "get_stock_assessment", forbidden)
    monkeypatch.setattr(collect, "get_price_history", forbidden)
    result = collect.collect_report("TEST", "entry-1")
    assert result.assessment["scores"]["overall"] == 42
    assert len(result.journal) == 1
    assert "linked_entry_id" in queries[0]
    with pytest.raises(LookupError):
        collect.collect_report("OTHER", "entry-1")
