from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.market import MarketClosePair


client = TestClient(app)


def test_home_contract_tolerates_partial_sources(monkeypatch) -> None:
    from app.api.v1 import home as home_api

    monkeypatch.setattr(home_api, "get_home_dashboard", lambda: {
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


def test_home_service_reads_only_persisted_helpers(monkeypatch) -> None:
    from app.services import home

    monkeypatch.setattr(home, "get_workspace_state", lambda: None)
    monkeypatch.setattr(home, "_market_summary", lambda: {"indices": [], "as_of": "2026-09-28"})
    monkeypatch.setattr(home, "get_data_quality_summary", lambda: None)
    monkeypatch.setattr(home.daily_opportunities, "get_top_daily", lambda: {"rows": [], "status": "not_ready"})
    monkeypatch.setattr(home, "_portfolio_summary", lambda: {"positions_count": 0, "positions": [], "tickers": []})
    monkeypatch.setattr(home.sell_state_repository, "list_ranking_snapshot", lambda: ([], None, ""))
    monkeypatch.setattr(home.stock_assessments, "list_all_snapshots", lambda *_: [])
    monkeypatch.setattr(home.industry_group_repository, "list_home_rankings", lambda **_: (None, []))
    monkeypatch.setattr(home.earnings_repository, "next_earnings_dates", lambda *_: {})
    monkeypatch.setattr(home.daily_opportunities, "get_home_changes", lambda **_: {"rows": [], "as_of": None, "previous_as_of": None})

    payload = home.get_home_dashboard()

    assert payload["sell_rows"] == []
    assert payload["opportunities"] == []
    assert payload["market"]["indices"] == []
