"""A cached intraday candle cannot become a final close just because time passed."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domain.chart_patterns import detect_patterns
from app.services import chart_analysis as service
from app.services.market_calendar import (
    ExpectedMarketSession,
    completed_ticker_market_session as calendar_completed_session,
)
from scripts.evaluate_published_chart_examples import bars_for, cases, matching


@pytest.fixture
def quotes(monkeypatch):
    # This frozen source example is first confirmed by the 7 August breakout.
    source = next(case for case in cases() if case["ticker"] == "ADSK")
    bars = [bar for bar in bars_for(source) if bar.date <= date(2009, 8, 7)]
    reference = matching(source, detect_patterns("ADSK", bars))[0]
    assert reference.detected_on == reference.breakout_on == "2009-08-07"
    close_at = datetime(2009, 8, 7, 20, tzinfo=UTC)
    session = ExpectedMarketSession(date=close_at.date(), phase="closed", close_at=close_at)
    rows = [
        SimpleNamespace(
            **bar.__dict__,
            fetched_at=datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=21),
            source="yfinance",
            adj_close=bar.close,
        )
        for bar in bars
    ]
    rows[-1].fetched_at = close_at - timedelta(hours=1)
    monkeypatch.setattr(service.repository, "_read_json_setting", lambda key: {})
    monkeypatch.setattr(service, "list_price_bars", lambda *args, **kwargs: rows)
    monkeypatch.setattr(service, "completed_ticker_market_session", lambda *args, **kwargs: session)
    monkeypatch.setattr(service, "_split_events", lambda ticker: {})

    def no_write_or_network(*args, **kwargs):
        raise AssertionError("Reading chart quality must not write or refresh provider data")

    monkeypatch.setattr(service.repository, "_write_json_setting", no_write_or_network)
    monkeypatch.setattr(service, "repair_chart_history", no_write_or_network)
    return SimpleNamespace(rows=rows, bars=bars, reference=reference, session=session)


def test_prepare_excludes_the_unverified_newest_session_without_changing_cached_values(quotes):
    last = quotes.rows[-1]
    original = dict(vars(last))
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session
    )
    assert quality.partial and quality.excluded_bar_count == 1
    assert any(
        issue["code"] == "incomplete_session" and issue["date"] == last.date.isoformat()
        for issue in quality.issues
    )
    assert all(bar.date < last.date for segment in quality.segments for bar in segment)
    assert vars(last) == original


def test_analyse_hides_intraday_close_and_cannot_confirm_its_breakout(quotes):
    chart = service.analyse("ADSK")
    assert chart["as_of"] == quotes.session.date.isoformat()
    assert chart["price_as_of"] == quotes.rows[-2].date.isoformat()
    assert chart["stale"] is True
    assert chart["quality"]["partial"]
    point = chart["points"][-1]
    assert point["date"] == "2009-08-07" and point["excluded"] is True
    assert all(point[field] is None for field in ("open", "high", "low", "close", "volume"))
    assert not any(pattern["id"] == quotes.reference.id for pattern in chart["patterns"])
    assert all(
        pattern["detected_on"] < "2009-08-07"
        and pattern["breakout_on"] != "2009-08-07"
        and all(point["date"] < "2009-08-07" for point in pattern["points"])
        for pattern in chart["patterns"]
    )


@pytest.mark.parametrize("seconds_after_close", [0, 1, 3600])
def test_fetch_at_or_after_close_is_included_and_confirms_the_frozen_breakout(
    quotes, seconds_after_close
):
    quotes.rows[-1].fetched_at = quotes.session.close_at + timedelta(seconds=seconds_after_close)
    chart = service.analyse("ADSK")
    assert chart["price_as_of"] == "2009-08-07" and chart["stale"] is False
    assert chart["points"][-1]["close"] == quotes.bars[-1].close
    assert chart["points"][-1]["excluded"] is False
    assert not any(issue["code"] == "incomplete_session" for issue in chart["quality"]["issues"])
    found = next(pattern for pattern in chart["patterns"] if pattern["id"] == quotes.reference.id)
    assert found["detected_on"] == found["breakout_on"] == "2009-08-07"


@pytest.mark.parametrize("missing_attribute", [False, True])
def test_missing_fetch_timestamp_is_conservative_for_the_newest_session(quotes, missing_attribute):
    if missing_attribute:
        del quotes.rows[-1].fetched_at
    else:
        quotes.rows[-1].fetched_at = None
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session
    )
    assert quality.partial
    assert all(bar.date < quotes.session.date for segment in quality.segments for bar in segment)
    assert any(issue["code"] == "incomplete_session" for issue in quality.issues)


@pytest.mark.parametrize("hour,included", [(19, False), (20, True), (21, True)])
def test_naive_fetch_timestamp_is_interpreted_as_utc(quotes, hour, included):
    quotes.rows[-1].fetched_at = datetime(2009, 8, 7, hour)
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session
    )
    present = any(
        bar.date == quotes.session.date for segment in quality.segments for bar in segment
    )
    assert present is included


def test_aware_fetch_timestamp_compares_the_actual_instant(quotes):
    # 22:00 at UTC+2 is exactly the 20:00 UTC close, not a later session.
    quotes.rows[-1].fetched_at = datetime(2009, 8, 7, 22, tzinfo=timezone(timedelta(hours=2)))
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session
    )
    assert any(bar.date == quotes.session.date for segment in quality.segments for bar in segment)
    assert not any(issue["code"] == "incomplete_session" for issue in quality.issues)


def test_future_rows_are_clipped_before_deciding_which_completed_bar_is_verified(quotes):
    later = SimpleNamespace(**vars(quotes.rows[-1]))
    later.date = date(2009, 8, 10)
    later.fetched_at = datetime(2009, 8, 10, 21, tzinfo=UTC)
    quotes.rows.append(later)
    bars, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session
    )
    assert all(bar.date <= quotes.session.date for bar in bars)
    assert any(issue["code"] == "incomplete_session" for issue in quality.issues)
    chart = service.analyse("ADSK", as_of=date(2099, 1, 1))
    assert chart["as_of"] == "2009-08-07"
    assert all(point["date"] <= "2009-08-07" for point in chart["points"])
    assert chart["points"][-1]["excluded"] is True


def test_historical_cutoff_keeps_legacy_quotes_without_using_todays_close(quotes):
    cutoff = quotes.rows[-2].date
    for row in quotes.rows:
        row.fetched_at = None
    bars, quality = service._prepare_rows(quotes.rows, cutoff=cutoff, session=quotes.session)
    assert max(bar.date for bar in bars) == cutoff
    assert max(bar.date for segment in quality.segments for bar in segment) == cutoff
    assert not any(issue["code"] == "incomplete_session" for issue in quality.issues)
    chart = service.analyse("ADSK", as_of=cutoff)
    assert chart["price_as_of"] == cutoff.isoformat() and chart["stale"] is False
    assert chart["points"][-1]["close"] == quotes.bars[-2].close
    assert chart["points"][-1]["excluded"] is False
    assert not any(issue["code"] == "incomplete_session" for issue in chart["quality"]["issues"])


def _enable_scan(quotes, monkeypatch, rows_by_ticker=None):
    rows_by_ticker = rows_by_ticker or {"ADSK": quotes.rows}
    store = {}
    monkeypatch.setattr(
        service.repository, "_read_json_setting", lambda key: deepcopy(store.get(key, {}))
    )
    monkeypatch.setattr(
        service.repository,
        "_write_json_setting",
        lambda key, value, **kwargs: store.update({key: deepcopy(value)}),
    )
    monkeypatch.setattr(
        service,
        "_scan_stocks",
        lambda: [(ticker, ticker, ticker, {}) for ticker in rows_by_ticker],
    )
    monkeypatch.setattr(
        service,
        "list_price_bars_for_tickers",
        lambda tickers, **kwargs: {ticker: rows_by_ticker[ticker] for ticker in tickers},
    )
    monkeypatch.setattr(service, "list_price_bars", lambda ticker, **kwargs: rows_by_ticker[ticker])
    return store


def test_scan_does_not_promote_the_cached_intraday_candle_after_market_close(quotes, monkeypatch):
    store = _enable_scan(quotes, monkeypatch)
    service.scan_universe(repair_prices=False)
    snapshot = store[service.RESULT_KEY]
    assert snapshot["partial_count"] == 1
    assert snapshot["quality_counts"]["incomplete_session"] == 1
    assert not any(pattern["id"] == quotes.reference.id for pattern in snapshot["patterns"])
    assert all(
        pattern["segment_end"] <= quotes.rows[-2].date.isoformat()
        and pattern["breakout_on"] != "2009-08-07"
        for pattern in snapshot["patterns"]
    )


def test_scan_freezes_each_session_once_across_repair_preflight_recheck_and_analysis(
    quotes, monkeypatch
):
    rows = {
        "ADSK": quotes.rows,
        "SECOND": [SimpleNamespace(**vars(row)) for row in quotes.rows],
    }
    store = _enable_scan(quotes, monkeypatch, rows)
    session_calls, repaired, prepared = [], [], []

    def one_session(ticker):
        assert ticker not in session_calls, "Session must remain frozen during a scan"
        session_calls.append(ticker)
        return quotes.session

    original_prepare = service._prepare_rows

    def prepare(observations, *, cutoff, session=None, ticker=None):
        prepared.append(session)
        return original_prepare(observations, cutoff=cutoff, session=session, ticker=ticker)

    def repair(ticker, *args, **kwargs):
        repaired.append(ticker)
        rows[ticker][-1].fetched_at = quotes.session.close_at + timedelta(minutes=1)
        return {"records_written": len(rows[ticker]), "reason_code": "repaired"}

    monkeypatch.setattr(service, "completed_ticker_market_session", one_session)
    monkeypatch.setattr(service, "_prepare_rows", prepare)
    monkeypatch.setattr(service, "repair_chart_history", repair)
    service.scan_universe(repair_prices=True)
    assert sorted(session_calls) == sorted(rows)
    assert sorted(repaired) == sorted(rows)
    assert len(prepared) >= 3 * len(rows)
    assert all(session is quotes.session for session in prepared)
    snapshot = store[service.RESULT_KEY]
    assert snapshot["repair_summary"]["succeeded"] == 2
    assert snapshot["partial_count"] == 0
    assert any(pattern["id"] == quotes.reference.id for pattern in snapshot["patterns"])


def test_duplicate_current_date_with_mixed_fetch_times_is_entirely_excluded(quotes):
    early = quotes.rows[-1]
    late = SimpleNamespace(**vars(early))
    late.fetched_at = quotes.session.close_at + timedelta(minutes=1)
    quotes.rows.append(late)
    for observations in ((early, late), (late, early)):
        quotes.rows[-2:] = observations
        _, quality = service._prepare_rows(
            quotes.rows, cutoff=quotes.session.date, session=quotes.session
        )
        assert quality.excluded_bar_count == 2
        assert all(
            bar.date < quotes.session.date for segment in quality.segments for bar in segment
        )
        chart = service.analyse("ADSK")
        current = [point for point in chart["points"] if point["date"] == "2009-08-07"]
        assert len(current) == 2
        assert all(point["excluded"] and point["close"] is None for point in current)
        assert chart["price_as_of"] == quotes.rows[-3].date.isoformat() and chart["stale"]
        assert not any(pattern["id"] == quotes.reference.id for pattern in chart["patterns"])


def _move_reference_to_friday(quotes, friday):
    shift = friday - quotes.rows[-1].date
    for row in quotes.rows:
        row.date += shift
        # These older reference observations represent a later history fetch;
        # only the newest Friday gets a same-day retrieval in the actual test.
        row.fetched_at = datetime.combine(row.date, datetime.min.time(), tzinfo=UTC) + timedelta(
            days=1, hours=21
        )


def test_fridays_intraday_quote_remains_unverified_after_mondays_session_closes(
    quotes, monkeypatch
):
    friday = date(2026, 10, 23)
    _move_reference_to_friday(quotes, friday)
    monday = calendar_completed_session("ADSK", now=datetime(2026, 10, 26, 22, tzinfo=UTC))
    friday_session = calendar_completed_session("ADSK", now=datetime(2026, 10, 23, 23, tzinfo=UTC))
    quotes.rows[-1].fetched_at = friday_session.close_at - timedelta(minutes=30)
    monkeypatch.setattr(
        service,
        "completed_ticker_market_session",
        lambda ticker, now=None: calendar_completed_session(ticker, now=now) if now else monday,
    )
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=monday.date, session=monday, ticker="ADSK"
    )
    assert any(
        issue["code"] == "incomplete_session" and issue["date"] == friday.isoformat()
        for issue in quality.issues
    )
    assert all(bar.date < friday for segment in quality.segments for bar in segment)
    chart = service.analyse("ADSK")
    assert chart["as_of"] == "2026-10-26"
    assert chart["price_as_of"] == "2026-10-22" and chart["stale"] is True
    assert chart["points"][-1]["date"] == friday.isoformat()
    assert chart["points"][-1]["close"] is None
    assert chart["points"][-1]["excluded"] is True
    assert all(pattern["breakout_on"] != friday.isoformat() for pattern in chart["patterns"])


def test_previous_friday_uses_its_own_us_close_across_the_dst_change(quotes, monkeypatch):
    friday = date(2026, 10, 30)
    _move_reference_to_friday(quotes, friday)
    monday = calendar_completed_session("ADSK", now=datetime(2026, 11, 2, 22, tzinfo=UTC))
    friday_session = calendar_completed_session("ADSK", now=datetime(2026, 10, 30, 23, tzinfo=UTC))
    assert friday_session.close_at == datetime(2026, 10, 30, 20, tzinfo=UTC)
    assert monday.close_at == datetime(2026, 11, 2, 21, tzinfo=UTC)
    monkeypatch.setattr(
        service,
        "completed_ticker_market_session",
        lambda ticker, now=None: calendar_completed_session(ticker, now=now) if now else monday,
    )

    # 20:30 UTC is a final Friday quote, even though Monday closes at 21:00 UTC.
    quotes.rows[-1].fetched_at = datetime(2026, 10, 30, 20, 30, tzinfo=UTC)
    _, final_quality = service._prepare_rows(
        quotes.rows, cutoff=monday.date, session=monday, ticker="ADSK"
    )
    assert any(bar.date == friday for segment in final_quality.segments for bar in segment)
    assert not any(issue["code"] == "incomplete_session" for issue in final_quality.issues)
    chart = service.analyse("ADSK")
    assert chart["price_as_of"] == friday.isoformat()
    assert chart["points"][-1]["close"] == quotes.rows[-1].close

    quotes.rows[-1].fetched_at = datetime(2026, 10, 30, 19, 59, tzinfo=UTC)
    _, early_quality = service._prepare_rows(
        quotes.rows, cutoff=monday.date, session=monday, ticker="ADSK"
    )
    assert all(bar.date < friday for segment in early_quality.segments for bar in segment)
    assert any(issue["code"] == "incomplete_session" for issue in early_quality.issues)


def test_known_intraday_quote_inside_the_cup_is_a_boundary_for_pattern_detection(quotes):
    middle = next(row for row in quotes.rows if row.date == date(2009, 7, 8))
    middle.fetched_at = datetime(2009, 7, 8, 19, tzinfo=UTC)
    quotes.rows[-1].fetched_at = quotes.session.close_at + timedelta(minutes=1)
    _, quality = service._prepare_rows(
        quotes.rows, cutoff=quotes.session.date, session=quotes.session, ticker="ADSK"
    )
    assert quality.partial and quality.excluded_bar_count == 1
    assert quality.boundary_count == 1
    assert any(
        issue["code"] == "incomplete_session" and issue["date"] == middle.date.isoformat()
        for issue in quality.issues
    )
    assert all(
        not segment[0].date <= middle.date <= segment[-1].date for segment in quality.segments
    )
    chart = service.analyse("ADSK")
    point = next(point for point in chart["points"] if point["date"] == "2009-07-08")
    assert point["excluded"] is True and point["close"] is None
    assert chart["points"][-1]["close"] == quotes.bars[-1].close
    assert not any(pattern["id"] == quotes.reference.id for pattern in chart["patterns"])
    assert all(
        not pattern["start_date"] < "2009-07-08" < pattern["end_date"]
        for pattern in chart["patterns"]
    )
