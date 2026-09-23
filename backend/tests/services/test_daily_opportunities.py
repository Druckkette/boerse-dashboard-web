from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.services import daily_opportunities as daily
from app.services.market_calendar import expected_us_market_session, previous_us_market_session_date


DAY = date(2026, 9, 22)


def item(ticker="GOOD", *, score=85, technical=80, rs=90, signals=None, **changes):
    row = {
        "ticker": ticker, "name": ticker, "as_of": DAY.isoformat(),
        "overall_score": score, "technical_score": technical, "fundamental_score": 75,
        "moving_average_score": 80, "chart_behavior_score": 75,
        "rs_rating": rs, "last_close": 100, "dollar_volume_mio": 80,
        "fundamentals_available": True, "rs_line_available": True,
        "volume_ratio_50d": 1.3, "checks": [
            {"category": "trend", "label": label, "passed": True} for label in (signals or [])
        ],
    }
    row.update(changes)
    return row


def bars(*tickers, stock_gain=0.01, spy_gain=0.005):
    result = {}
    for ticker in (*tickers, "SPY"):
        gain = spy_gain if ticker == "SPY" else stock_gain
        result[ticker] = [
            (DAY - timedelta(days=6 - index), 100 * (1 + gain) ** index,
             datetime(2026, 9, 22, 21, tzinfo=UTC))
            for index in range(7)
        ]
    return result


def ranked(items, previous=None, *, price_bars=None):
    return daily.calculate_daily_rows(
        items, previous or {}, price_bars or bars(*(row["ticker"] for row in items)),
        day=DAY, require_fresh_price=False,
    )


def test_improving_high_quality_stock_rises_above_stable_peer():
    rows = ranked([item("RISING", score=85), item("STABLE", score=86)], {
        "RISING": {"overall_score": 80, "technical_score": 72, "rs_rating": 83, "signals_json": [], "rank": 4},
        "STABLE": {"overall_score": 86, "technical_score": 80, "rs_rating": 90, "signals_json": [], "rank": 1},
    })
    assert rows[0]["rank"] == 1
    assert rows[0]["details_json"]["previous_rank"] == 4
    assert rows[0]["details_json"]["overall_score_delta"] == 5


def test_short_term_spike_does_not_admit_weak_stock():
    candidates = [item("STRONG"), item("WEAK", score=60)]
    price_bars = bars("STRONG", "WEAK")
    price_bars["WEAK"][-1] = (DAY, 200, price_bars["WEAK"][-1][2])
    rows = ranked(candidates, price_bars=price_bars)
    assert rows[0]["rank"] == 1
    assert rows[1]["rank"] is None


def test_stable_leader_is_not_rotated_out():
    rows = ranked([item("LEADER", score=96), item("CHALLENGER", score=80)], {
        "LEADER": {"overall_score": 96, "technical_score": 80, "rs_rating": 90, "signals_json": [], "rank": 1},
    })
    assert rows[0]["rank"] == 1
    assert rows[0]["details_json"]["previous_rank"] == 1


def test_falling_rs_reduces_dynamics():
    old = {"overall_score": 85, "technical_score": 80, "rs_rating": 95, "signals_json": []}
    falling = ranked([item(rs=85)], {"GOOD": old})[0]
    stable = ranked([item(rs=95)], {"GOOD": old})[0]
    assert falling["daily_dynamics_score"] < stable["daily_dynamics_score"]
    assert falling["details_json"]["rs_rating_delta"] == -10


def test_new_positive_signal_beats_existing_signal():
    current = item(signals=["Kurs über 21 EMA"])
    baseline = {"overall_score": 85, "technical_score": 80, "rs_rating": 90, "signals_json": []}
    new = ranked([current], {"GOOD": baseline})[0]
    old = ranked([current], {"GOOD": {**baseline, "signals_json": ["Kurs über 21 EMA"]}})[0]
    assert new["daily_dynamics_score"] > old["daily_dynamics_score"]
    assert "Neu: Kurs über 21 EMA" in new["details_json"]["positive_changes"]
    assert "Neu: Kurs über 21 EMA" not in old["details_json"]["positive_changes"]


def test_missing_or_stale_data_excludes_candidates():
    candidates = [item("FRESH"), item("STALE", as_of="2026-09-21"),
                  item("NO_RS", rs=None), item("NO_FUND", fundamentals_available=False),
                  item("LOW_LIQ", dollar_volume_mio=2)]
    rows = ranked(candidates)
    assert [(row["ticker"], row["rank"]) for row in rows] == [
        ("FRESH", 1), ("NO_RS", None), ("NO_FUND", None), ("LOW_LIQ", None),
    ]
    assert ranked([item("MISSING_PRICE")], price_bars={"SPY": bars()["SPY"]})[0]["rank"] is None


def test_negative_volume_cannot_create_positive_bonus():
    price_bars = bars("GOOD")
    price_bars["GOOD"][-1] = (DAY, 90, price_bars["GOOD"][-1][2])
    row = ranked([item(volume_ratio_50d=2)], price_bars=price_bars)[0]
    assert row["details_json"]["components"]["volume"] < 50


def test_us_calendar_handles_weekend_and_previous_session():
    session = expected_us_market_session(datetime(2026, 9, 26, 12, tzinfo=UTC))
    assert session.date == date(2026, 9, 25)
    assert previous_us_market_session_date(date(2026, 9, 28)) == date(2026, 9, 25)


def test_ties_are_sorted_by_quality_then_ticker():
    rows = ranked([item("BBB"), item("AAA")])
    assert sorted(rows, key=lambda row: row["rank"])[0]["ticker"] == "AAA"


def test_api_uses_only_saved_rows_and_supports_fewer_than_three(monkeypatch):
    monkeypatch.setattr(daily, "get_top_daily", lambda: {
        "as_of": DAY.isoformat(), "generated_at": None, "status": "current", "rows": [],
    })
    response = TestClient(app).get("/api/v1/stocks/top-daily")
    assert response.status_code == 200
    assert response.json()["rows"] == []
