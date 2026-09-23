from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.domain.stocks.assessment import StockAssessmentBar, compute_stock_assessment
from app.main import app
from app.services import stock_screening as screening
from app.repositories.market import MarketRepositoryUnavailable
from app.workers.tasks.common import JobCancelled


def inputs():
    start = date(2025, 1, 1)
    bars = [StockAssessmentBar(
        date=start + timedelta(days=i), open=100 + i, high=102 + i,
        low=99 + i, close=101 + i, volume=1_000_000,
    ) for i in range(260)]
    return {"bars": bars, "rs_context": {}, "fundamentals_context": {}, "institutional_context": {}}


@pytest.fixture
def storage(monkeypatch):
    from app.services import daily_opportunities
    monkeypatch.setattr(daily_opportunities, "refresh_top_daily", lambda writes: {"qualified_count": 0})
    state = {"rows": [], "publications": 0}
    monkeypatch.setattr(screening.stock_assessments, "list_all_snapshots", lambda tickers=None: state["rows"])

    def publish(rows, **kwargs):
        state["rows"] = [SimpleNamespace(ticker=row.ticker, item_json=row.item_json) for row in rows]
        state["publications"] += 1
        return len(rows)

    monkeypatch.setattr(screening.stock_assessments, "replace_snapshots", publish)
    return state


def test_entire_universe_is_processed_in_bounded_batches_without_rs_preselection(monkeypatch, storage):
    tickers = [f"STOCK{i}" for i in range(5026)]
    data = inputs()
    reference = compute_stock_assessment("STOCK0", **data)
    batches = []
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: tickers)

    def load(values, *, strict):
        assert strict
        batches.append(values)
        return [(ticker, None, data) for ticker in values]

    monkeypatch.setattr(screening, "_load_assessment_inputs", load)
    monkeypatch.setattr(screening.assessment, "compute_stock_assessment", lambda ticker, **kwargs: replace(reference, ticker=ticker))
    monkeypatch.setattr(screening, "input_fingerprint", lambda *args, **kwargs: "same-input")
    result = screening.screen_universe()

    assert result["records_written"] == 5026
    assert max(map(len, batches)) <= 40
    assert [ticker for batch in batches for ticker in batch] == tickers
    assert storage["publications"] == 1
    assert storage["rows"][-1].ticker == "STOCK5025"


def test_unchanged_inputs_reused_but_intraday_price_change_recomputed(monkeypatch, storage):
    data = inputs()
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: ["TWLO"])
    monkeypatch.setattr(screening, "_load_assessment_inputs", lambda *args, **kwargs: [("TWLO", None, data)])
    first = screening.screen_universe()
    expected = compute_stock_assessment("TWLO", **data)
    assert storage["rows"][0].item_json["overall_score"] == expected.scores.overall
    assert first["calculated_count"] == 1
    second = screening.screen_universe()
    assert second["reused_count"] == 1
    assert second["calculated_count"] == 0
    data["bars"][-1] = replace(data["bars"][-1], close=250)
    third = screening.screen_universe()
    assert third["calculated_count"] == 1
    assert third["reused_count"] == 0


def test_unchanged_revisions_do_not_load_price_history(monkeypatch, storage):
    data = inputs()
    loads = []
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: ["TWLO"])
    monkeypatch.setattr(screening.stock_assessments, "input_revisions", lambda: {"TWLO": "revision-1"})

    def load(tickers, **kwargs):
        loads.append(tickers)
        return [("TWLO", None, data)]

    monkeypatch.setattr(screening, "_load_assessment_inputs", load)
    screening.screen_universe()
    second = screening.screen_universe()
    assert loads == [["TWLO"]]
    assert second["reused_count"] == 1
    assert second["calculated_count"] == 0


def test_fingerprint_tracks_rules_fundamentals_rs_and_calendar():
    data = inputs()
    original = screening.input_fingerprint(data, engine_version="v1", today=date(2026, 9, 11))
    for changed in [
        {**data, "rs_context": {"rating": 95}},
        {**data, "fundamentals_context": {"annual_eps_growth_pct": 25}},
        {**data, "institutional_context": {"holders": 500}},
    ]:
        assert screening.input_fingerprint(changed, engine_version="v1", today=date(2026, 9, 11)) != original
    assert screening.input_fingerprint(data, engine_version="v2", today=date(2026, 9, 11)) != original
    assert screening.input_fingerprint(data, engine_version="v1", today=date(2026, 9, 12)) != original


def test_missing_prices_reported_and_not_scored_as_real_candidates(monkeypatch, storage):
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: ["READY", "EMPTY"])
    monkeypatch.setattr(screening, "_load_assessment_inputs", lambda *args, **kwargs: [
        ("READY", None, inputs()), ("EMPTY", None, {**inputs(), "bars": []}),
    ])
    result = screening.screen_universe()
    assert result["missing_tickers"] == ["EMPTY"]
    assert result["missing_count"] == 1
    assert result["partial"]
    assert result["records_written"] == 1
    assert not storage["rows"][0].item_json["fundamentals_available"]


def test_missing_prices_in_report_batch_do_not_fail_or_replace_snapshots(monkeypatch, storage):
    monkeypatch.setattr(screening, "_load_assessment_inputs", lambda *args, **kwargs: [
        ("EMPTY", None, {**inputs(), "bars": []}),
    ])

    result = screening.screen_universe(only_tickers=["EMPTY"])

    assert result["records_seen"] == 1
    assert result["records_written"] == 0
    assert result["missing_tickers"] == ["EMPTY"]
    assert result["errors"] == []
    assert storage["publications"] == 0


def test_calculation_error_in_report_batch_remains_an_error(monkeypatch, storage):
    monkeypatch.setattr(screening, "_load_assessment_inputs", lambda *args, **kwargs: [
        ("BROKEN", None, inputs()),
    ])

    def fail(*args, **kwargs):
        raise ValueError("invalid calculation")

    monkeypatch.setattr(screening.assessment, "compute_stock_assessment", fail)

    result = screening.screen_universe(only_tickers=["BROKEN"])

    assert result["ok"] is False
    assert result["errors"] == [{"ticker": "BROKEN", "error": "ValueError: invalid calculation"}]
    assert result["missing_tickers"] == []
    assert storage["publications"] == 0


@pytest.mark.parametrize("failure", [MarketRepositoryUnavailable("database offline"), JobCancelled("cancelled")])
def test_failure_or_cancel_preserves_previous_publication(monkeypatch, storage, failure):
    storage["rows"] = [SimpleNamespace(ticker="OLD", item_json={})]
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: ["NEW"])

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(screening, "_load_assessment_inputs", fail)
    with pytest.raises(type(failure)):
        screening.screen_universe()
    assert storage["publications"] == 0
    assert storage["rows"][0].ticker == "OLD"


def test_screening_api_returns_saved_scores_and_criteria_without_calculating(monkeypatch, storage):
    monkeypatch.setattr(screening.universes, "list_universe_tickers", lambda limit: ["TWLO"])
    monkeypatch.setattr(screening, "_load_assessment_inputs", lambda *args, **kwargs: [("TWLO", None, inputs())])
    screening.screen_universe()
    monkeypatch.setattr(screening.assessment, "compute_stock_assessment", lambda *args, **kwargs: pytest.fail("No live assessment in GET"))
    def query_saved(filters, *, expected_date, export=False):
        assert filters.page == 0
        return {
            "summary": storage["rows"][0].item_json["_screening"],
            "rows": [storage["rows"][0].item_json], "criteria": [], "total_count": 1,
        }

    monkeypatch.setattr(screening.stock_assessments, "query_screening", query_saved)
    response = TestClient(app).get("/api/v1/stocks/screening")
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["universe_count"] == 1
    assert result["rows"][0]["ticker"] == "TWLO"
    assert result["rows"][0]["checks"]
    assert "_input_fingerprint" not in result["rows"][0]


def test_export_includes_all_filtered_rows_and_escapes_spreadsheet_formulas(monkeypatch):
    from app.schemas import StockScreeningFilters
    item = {
        "ticker": "TWLO", "name": "=HYPERLINK(test)", "overall_score": 80,
        "technical_score": 80, "fundamental_score": 90, "moving_average_score": 100,
        "chart_behavior_score": 70, "warnings_count": 2, "as_of": "2026-09-11",
        "prices_stale": False, "checks": [{"label": "EPS", "passed": True, "detail": "3/3 Quartale"}],
    }
    def read(filters, *, export):
        assert export
        assert filters.min_score == 70
        assert filters.required == ["EPS"]
        return {"criteria": ["EPS"], "rows": [item] * 51}
    monkeypatch.setattr(screening, "get_screening", read)
    result = screening.screening_csv(StockScreeningFilters(min_score=70, required=["EPS"]))
    assert len(result.splitlines()) == 52
    assert "'=HYPERLINK(test)" in result
    assert "Erfüllt: 3/3 Quartale" in result
