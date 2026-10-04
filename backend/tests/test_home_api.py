from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.market import MarketClosePair


client = TestClient(app)


def test_home_contract_tolerates_partial_sources(monkeypatch) -> None:
    from app.api.v1 import home as home_api

    monkeypatch.setattr(home_api, "get_cached_home_dashboard", lambda: {
        "as_of": "2026-09-28", "errors": ["industry_groups"], "priorities": [],
        "priorities_total": 0, "review_positions_count": 0, "opportunities": [], "changes": [],
        "portfolio": {"positions_count": 0, "positions": []}, "industry_groups": [],
        "industry_groups_as_of": None, "watchlist": [], "watchlist_total": 0,
        "market": {"indices": []}, "data_quality": None,
    })

    response = client.get("/api/v1/home")

    assert response.status_code == 200
    assert response.json()["errors"] == ["industry_groups"]


def test_index_summary_uses_two_distinct_persisted_sessions(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(
        home.market_repository,
        "load_latest_close_pair",
        lambda ticker: [
            MarketClosePair(ticker=ticker, date=date(2026, 9, 25), close=100.0),
            MarketClosePair(ticker=ticker, date=date(2026, 9, 28), close=103.5),
        ],
    )
    monkeypatch.setattr(home, "completed_us_market_session", lambda: type("Session", (), {"date": date(2026, 9, 28)})())
    monkeypatch.setattr(home, "daily_bar_is_final", lambda *_: True)

    payload = home._index_summary("^GSPC", "S&P 500")

    assert payload == {
        "ticker": "^GSPC", "label": "S&P 500", "as_of": "2026-09-28",
        "previous_as_of": "2026-09-25", "close": 103.5, "previous_close": 100.0,
        "change_pct": 3.5, "status": "available",
    }


def test_index_summary_marks_missing_previous_close_as_partial(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(
        home.market_repository, "load_latest_close_pair",
        lambda ticker: [MarketClosePair(ticker=ticker, date=date(2026, 9, 28), close=100.0)],
    )
    monkeypatch.setattr(home, "completed_us_market_session", lambda: type("Session", (), {"date": date(2026, 9, 28)})())
    monkeypatch.setattr(home, "daily_bar_is_final", lambda *_: True)

    payload = home._index_summary("^IXIC", "Nasdaq")

    assert payload["status"] == "partial"
    assert payload["previous_close"] is None
    assert payload["change_pct"] is None


def test_index_summary_ignores_unconfirmed_intraday_close(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(
        home.market_repository,
        "load_latest_close_pair",
        lambda ticker: [
            MarketClosePair(ticker=ticker, date=date(2026, 9, 25), close=100.0),
            MarketClosePair(ticker=ticker, date=date(2026, 9, 28), close=102.0),
            MarketClosePair(ticker=ticker, date=date(2026, 9, 29), close=99.0),
        ],
    )
    monkeypatch.setattr(home, "completed_us_market_session", lambda: type("Session", (), {"date": date(2026, 9, 28)})())
    monkeypatch.setattr(home, "daily_bar_is_final", lambda value, *_: value != date(2026, 9, 29))

    payload = home._index_summary("^GSPC", "S&P 500")

    assert payload["as_of"] == "2026-09-28"
    assert payload["previous_as_of"] == "2026-09-25"
    assert payload["change_pct"] == 2.0


def test_market_summary_reads_all_home_indices_in_one_batch(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(home, "expected_us_market_session", lambda: SimpleNamespace(phase="closed", date=date(2026, 9, 28)))
    monkeypatch.setattr(home, "completed_us_market_session", lambda: SimpleNamespace(date=date(2026, 9, 28)))
    monkeypatch.setattr(home.market_repository, "get_latest_market_snapshot", lambda: None)
    monkeypatch.setattr(home.market_repository, "list_breadth_daily", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(home, "_market_trend_ampel_for_ticker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(home, "daily_bar_is_final", lambda *_: True)
    calls: list[list[str]] = []

    def close_rows(tickers: list[str]) -> dict[str, list[MarketClosePair]]:
        calls.append(tickers)
        return {
            ticker: [
                MarketClosePair(ticker=ticker, date=date(2026, 9, 25), close=100.0),
                MarketClosePair(ticker=ticker, date=date(2026, 9, 28), close=101.0),
            ]
            for ticker in tickers
        }

    monkeypatch.setattr(home.market_repository, "load_latest_close_pairs", close_rows)

    payload = home._market_summary()

    assert calls == [["^VIX", "^GSPC", "^IXIC", "^RUT"]]
    assert [item["change_pct"] for item in payload["indices"]] == [1.0, 1.0, 1.0]


@pytest.fixture
def home_market_sources(monkeypatch):
    from app.services import home

    monkeypatch.setattr(home, "expected_us_market_session", lambda: SimpleNamespace(phase="closed", date=date(2026, 10, 2)))
    monkeypatch.setattr(home, "completed_us_market_session", lambda: SimpleNamespace(date=date(2026, 10, 2)))
    monkeypatch.setattr(home.market_repository, "list_breadth_daily", lambda *a, **k: [])
    monkeypatch.setattr(home.market_repository, "load_latest_close_pairs", lambda *a: {})
    monkeypatch.setattr(home, "_selected_market_ampel_logic", lambda: "ibd")
    trends = {ticker: SimpleNamespace(phase=phase, as_of="2026-10-02", price_data_complete=True, phase_reason="Test",
                                    powertrend_state="off", powertrend_formally_active=False,
                                    powertrend_start_date=None, powertrend_pressure_since=None)
              for ticker, phase in (("^GSPC", "rot"), ("^IXIC", "gelb_startschuss"), ("^RUT", "rot"))}
    calls = []

    def load(ticker, *, logic, lookback_days):
        calls.append((ticker, logic))
        trend = trends.get(ticker)
        if isinstance(trend, Exception):
            raise trend
        return trend

    monkeypatch.setattr(home, "_market_trend_ampel_for_ticker", load)
    return home, trends, calls


def test_home_mixed_index_phases_do_not_claim_the_whole_market_is_red(home_market_sources):
    home, _trends, calls = home_market_sources
    summary = home._market_summary()
    assert summary["phase"] == "mixed"
    assert summary["phase_label"] == "Uneinheitlich"
    assert summary["status"] == "available"
    assert [i["phase"] for i in summary["indices"]] == ["rot", "gelb_startschuss", "rot"]
    assert "Nasdaq Composite: Startschuss" in summary["summary"]
    assert calls == [("^GSPC", "ibd"), ("^IXIC", "ibd"), ("^RUT", "ibd")]


@pytest.mark.parametrize("phase", ["rot", "gelb_startschuss", "gruen", "aufwaertstrend", "gelb_trend_unter_druck", "neutral"])
def test_home_uniform_phase_requires_all_three_current_indices(home_market_sources, phase):
    home, trends, _calls = home_market_sources
    for trend in trends.values():
        trend.phase = phase
    assert home._market_summary()["phase"] == phase


@pytest.mark.parametrize("unavailable", [None, RuntimeError("source unavailable"), "stale", "incomplete"])
def test_home_cannot_promote_an_old_or_incomplete_index_phase(home_market_sources, unavailable):
    home, trends, _calls = home_market_sources
    if unavailable == "stale":
        trends["^IXIC"].as_of = "2026-10-01"
    elif unavailable == "incomplete":
        trends["^IXIC"].price_data_complete = False
    else:
        trends["^IXIC"] = unavailable
    summary = home._market_summary()
    assert summary["phase"] is None
    assert summary["status"] == "partial"
    assert summary["indices"][0]["phase"] == "rot"
    assert summary["indices"][1]["phase_status"] != "available"
    assert "2 von 3" in summary["summary"]


def test_attention_merges_changes_into_risk_rows_without_losing_priority():
    from app.services.home import _merge_attention_rows
    rows = _merge_attention_rows([
        {"ticker": "APP", "label": "Verkaufen", "tone": "bad", "detail": "Kurs unter 21-EMA · RS -4"},
    ], [
        {"ticker": "APP", "details": ["RS -4", "Gesamtscore -6"]},
        {"ticker": "AAPL", "scopes": ["watchlist"], "summary": "RS -3", "href": "/stocks/AAPL"},
    ])
    assert [row["ticker"] for row in rows] == ["APP", "AAPL"]
    assert rows[0]["label"] == "Verkaufen" and rows[0]["tone"] == "bad"
    assert rows[0]["detail"] == "Kurs unter 21-EMA · RS -4 · Gesamtscore -6"
    assert rows[1]["tone"] == "neutral"


def test_home_changes_are_one_row_per_ticker_and_keep_comparison_dates(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(home.daily_opportunities, "get_home_changes", lambda **_: {
        "as_of": "2026-09-28", "previous_as_of": "2026-09-25",
        "rows": [{
            "ticker": "APP", "rank": 1, "overall_score_delta": 6,
            "technical_score_delta": 2.5, "rs_rating_delta": 4,
            "positive_changes": ["Gesamtscore +6", "Technischer Score +2.5", "RS 93 → 97"],
        }],
    })

    rows = home._home_changes(portfolio_tickers={"APP"}, watchlist={"APP"})

    assert len(rows) == 1
    assert rows[0]["ticker"] == "APP"
    assert rows[0]["scopes"] == ["portfolio", "watchlist", "top_stocks"]
    assert rows[0]["details"] == ["Gesamtscore +6", "Technik +2.5", "RS +4"]
    assert rows[0]["previous_as_of"] == "2026-09-25"


def test_priorities_count_unique_review_positions_and_merge_earnings() -> None:
    from app.services import home

    priorities, review_count = home._priority_rows(
        [{
            "ticker": "APP", "status": "Verkaufen", "data_quality_status": "trusted",
            "primary_signal": "Kurs unter 21 EMA", "recommendation_pct": 100,
        }, {
            "ticker": "SPCX", "status": "Halten", "data_quality_status": "blocked",
            "data_quality_detail": "Zu wenig Kursdaten", "recommendation_pct": 0,
        }],
        {"APP": date.today()}, [], set(),
    )

    assert review_count == 2
    assert len(priorities) == 2
    assert priorities[0]["ticker"] == "APP"
    assert "Earnings heute" in priorities[0]["detail"]


def test_watchlist_keeps_tickers_without_assessment() -> None:
    from app.services import home

    rows = home._watchlist_rows(["APP", "MISSING"], [], failed=False)

    assert [row["ticker"] for row in rows] == ["APP", "MISSING"]
    assert all(row["data_status"] == "missing" for row in rows)


@pytest.mark.parametrize("open_tickers", [["SNDK"], []])
def test_home_service_reads_only_persisted_helpers(monkeypatch, open_tickers) -> None:
    from app.services import home

    monkeypatch.setattr(home, "get_workspace_state", lambda: None)
    monkeypatch.setattr(home, "_market_summary", lambda: {"indices": [], "as_of": "2026-09-28"})
    monkeypatch.setattr(home, "get_data_quality_summary", lambda: None)
    monkeypatch.setattr(home.daily_opportunities, "get_top_daily", lambda: {"rows": [], "status": "not_ready"})
    monkeypatch.setattr(home, "_portfolio_summary", lambda: {"positions_count": len(open_tickers), "positions": [], "tickers": open_tickers})
    monkeypatch.setattr(home.sell_state_repository, "list_ranking_snapshot", lambda: ([
        SimpleNamespace(model_dump=lambda **_: {"ticker": "APP", "status": "Verkaufen", "data_quality_status": "trusted"}),
        SimpleNamespace(model_dump=lambda **_: {"ticker": "SNDK", "status": "Verkaufen", "data_quality_status": "trusted"}),
    ], None, ""))
    monkeypatch.setattr(home.stock_assessments, "list_all_snapshots", lambda *_: [])
    monkeypatch.setattr(home.industry_group_repository, "list_home_rankings", lambda **_: (None, []))
    monkeypatch.setattr(home.earnings_repository, "next_earnings_dates", lambda *_: {})
    monkeypatch.setattr(home.daily_opportunities, "get_home_changes", lambda **_: {"rows": [], "as_of": None, "previous_as_of": None})

    payload = home.get_home_dashboard()

    assert [row["ticker"] for row in payload["sell_rows"]] == open_tickers
    assert [row["ticker"] for row in payload["priorities"]] == open_tickers
    assert payload["review_positions_count"] == len(open_tickers)
    assert payload["opportunities"] == []
    assert payload["market"]["indices"] == []


def test_home_cache_reuses_a_recent_persisted_snapshot(monkeypatch) -> None:
    from app.services import home

    calls = 0

    def dashboard() -> dict:
        nonlocal calls
        calls += 1
        return {"generated_at": str(calls)}

    monkeypatch.setattr(home, "get_home_dashboard", dashboard)
    monkeypatch.setattr(home, "_home_cache", None)

    assert home.get_cached_home_dashboard()["generated_at"] == "1"
    assert home.get_cached_home_dashboard()["generated_at"] == "1"
    assert calls == 1
    home._home_cache = None


def test_closing_position_invalidates_home_snapshot(monkeypatch) -> None:
    from app.api.v1 import portfolio as portfolio_api
    from app.schemas import PortfolioPositionDeleteResponse
    from app.services import home

    monkeypatch.setattr(home, "_home_cache", (0, "ibd", {"priorities": [{"ticker": "APP"}]}))
    monkeypatch.setattr(portfolio_api, "delete_portfolio_position", lambda ticker: PortfolioPositionDeleteResponse(ticker=ticker, closed=True))

    response = client.delete("/api/v1/portfolio/positions/APP")

    assert response.status_code == 200
    assert response.json()["closed"] is True
    assert home._home_cache is None


@pytest.mark.parametrize("phase,state", [("rot", "on"), ("aufwaertstrend", "under_pressure")])
def test_home_keeps_index_powertrend_independent_of_market_phase(home_market_sources, phase, state):
    home, trends, _ = home_market_sources
    sp500 = trends["^GSPC"]
    sp500.phase = phase
    sp500.powertrend_state = state
    sp500.powertrend_formally_active = True
    sp500.powertrend_start_date = "2026-08-19"
    sp500.powertrend_pressure_since = "2026-09-10" if state == "under_pressure" else None
    index = home._market_summary()["indices"][0]
    assert index["phase"] == phase
    assert index["powertrend"]["state"] == state
    assert index["powertrend"]["start_date"] == "2026-08-19"
    assert index["powertrend"]["pressure_since"] == sp500.powertrend_pressure_since
    assert index["powertrend"]["enabled"]
