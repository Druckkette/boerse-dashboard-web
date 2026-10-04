from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.services import freshness


def test_freshness_reports_trend_benchmark_separately(monkeypatch) -> None:
    class FakeResult:
        def all(self):
            return [
                ("^GSPC", date(2026, 6, 12)),
                ("SPY", date(2026, 6, 16)),
            ]

    class FakeSession:
        def __init__(self) -> None:
            self.scalar_values = [
                date(2026, 6, 16),
                date(2026, 3, 31),
                datetime(2026, 6, 16, 12, tzinfo=UTC),
                "nasdaq",
                datetime.now(UTC),
                12,
            ]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalar(self, _query):
            return self.scalar_values.pop(0)

        def execute(self, _query):
            return FakeResult()

    monkeypatch.setattr(freshness, "SessionLocal", FakeSession)
    expected_session = freshness.ExpectedMarketSession(date=date(2026, 6, 16), phase="closed")
    monkeypatch.setattr(freshness, "expected_us_market_session", lambda now=None: expected_session)
    monkeypatch.setattr(
        freshness,
        "_price_universe_freshness",
        lambda db, now, expected: freshness.ServiceFreshness(
            name="prices",
            status="fresh",
            as_of="2026-06-16",
            lag_minutes=60,
        ),
    )
    monkeypatch.setattr(
        freshness,
        "_breadth_freshness",
        lambda db, now, expected: freshness.ServiceFreshness(
            name="market_breadth",
            status="fresh",
            as_of="2026-06-16",
            lag_minutes=60,
        ),
    )
    monkeypatch.setattr(
        freshness,
        "_relative_strength_freshness",
        lambda db, now, expected: freshness.ServiceFreshness(
            name="relative_strength",
            status="fresh",
            as_of="2026-06-16",
            lag_minutes=60,
        ),
    )
    monkeypatch.setattr(
        freshness,
        "_tracked_fundamentals_freshness",
        lambda db, now: freshness.ServiceFreshness(
            name="fundamentals_tracked",
            status="fresh",
            as_of="2026-06-16",
            lag_minutes=60,
        ),
    )

    result = freshness.get_freshness()
    services = {service.name: service for service in result.services}

    assert services["prices"].as_of == "2026-06-16"
    assert services["market_snapshot"].as_of == "2026-06-16"
    assert services["trend_benchmark"].as_of == "2026-06-12"
    assert services["trend_benchmark"].metadata["used_ticker"] == "^GSPC"
    assert services["trend_benchmark"].metadata["candidate_dates"] == {
        "^GSPC": "2026-06-12",
        "SPY": "2026-06-16",
    }
    assert services["fundamentals_tracked"].as_of == "2026-06-16"
    assert services["earnings_calendar"].metadata["source"] == "nasdaq"
    assert "(Nasdaq)" in services["earnings_calendar"].detail
    assert services["institutional_13f"].as_of == "2026-03-31"
    assert services["institutional_13f"].metadata["expected_interval"] == "quarterly"
    assert services["sell_ranking"].status == "fresh"
    assert services["sell_ranking"].metadata["position_count"] == 12


def test_13f_freshness_respects_sec_filing_deadline() -> None:
    before_deadline = freshness._institutional_13f_freshness(
        datetime(2026, 7, 31, 12, tzinfo=UTC),
        date(2026, 3, 31),
    )
    after_deadline = freshness._institutional_13f_freshness(
        datetime(2026, 8, 15, 12, tzinfo=UTC),
        date(2026, 3, 31),
    )

    assert before_deadline.status == "fresh"
    assert before_deadline.metadata["required_report_period"] == "2026-03-31"
    assert before_deadline.metadata["next_report_period"] == "2026-06-30"
    assert after_deadline.status == "stale"
    assert after_deadline.metadata["required_report_period"] == "2026-06-30"


def test_sell_ranking_stays_fresh_after_latest_market_close() -> None:
    session = freshness.ExpectedMarketSession(
        date=date(2026, 7, 31),
        phase="closed",
        open_at=datetime(2026, 7, 31, 13, 30, tzinfo=UTC),
        close_at=datetime(2026, 7, 31, 20, tzinfo=UTC),
    )

    result = freshness._sell_ranking_freshness(
        datetime(2026, 8, 1, 14, tzinfo=UTC),
        datetime(2026, 7, 31, 21, 32, tzinfo=UTC),
        12,
        expected_session=session,
    )

    assert result.status == "fresh"
    assert result.metadata["expected_as_of"] == "2026-07-31"


def test_sell_ranking_stays_fresh_during_same_open_session() -> None:
    session = freshness.ExpectedMarketSession(
        date=date(2026, 7, 31),
        phase="intraday",
        open_at=datetime(2026, 7, 31, 13, 30, tzinfo=UTC),
        close_at=datetime(2026, 7, 31, 20, tzinfo=UTC),
    )

    result = freshness._sell_ranking_freshness(
        datetime(2026, 7, 31, 16, tzinfo=UTC),
        datetime(2026, 7, 31, 15, 50, tzinfo=UTC),
        12,
        expected_session=session,
    )

    assert result.status == "fresh"
    assert result.metadata["expected_interval"] == "per_market_session"


def test_sell_ranking_requires_refresh_after_market_opens() -> None:
    session = freshness.ExpectedMarketSession(
        date=date(2026, 7, 31),
        phase="intraday",
        open_at=datetime(2026, 7, 31, 13, 30, tzinfo=UTC),
        close_at=datetime(2026, 7, 31, 20, tzinfo=UTC),
    )

    result = freshness._sell_ranking_freshness(
        datetime(2026, 7, 31, 16, tzinfo=UTC),
        datetime(2026, 7, 31, 12, tzinfo=UTC),
        12,
        expected_session=session,
    )

    assert result.status == "stale"


@pytest.mark.parametrize("stock_date,expected_status", [(date(2026, 10, 3), "fresh"), (date(2026, 9, 14), "stale")])
def test_etfs_do_not_age_or_block_tracked_fundamentals(monkeypatch, stock_date, expected_status):
    from types import SimpleNamespace
    monkeypatch.setattr(freshness, "_tracked_fundamental_tickers", lambda db: ["ARKK.L", "ZPDH.DE", "FUND", "AAPL"])
    profiles = [SimpleNamespace(ticker=ticker, name=ticker, asset_class="stock", metadata_json={}) for ticker in ("ARKK.L", "ZPDH.DE", "AAPL")]
    profiles.append(SimpleNamespace(ticker="FUND", name="Example", asset_class="etf", metadata_json={}))
    class Result:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows
    class Session:
        def scalars(self, query): return Result(profiles)
        def execute(self, query):
            tickers = query.compile().params["ticker_1"]
            assert tickers == ["AAPL"]
            return Result([("AAPL", stock_date)])
    result = freshness._tracked_fundamentals_freshness(Session(), datetime(2026, 10, 4, tzinfo=UTC))
    assert result.status == expected_status
    assert result.as_of == stock_date.isoformat()
    assert result.metadata["excluded_etf_tickers"] == ["ARKK.L", "FUND", "ZPDH.DE"]
    assert result.metadata["missing_tickers"] == []


def test_only_etfs_need_no_fundamental_check(monkeypatch):
    monkeypatch.setattr(freshness, "_tracked_fundamental_tickers", lambda db: ["ARKK.L", "ZPDH.DE"])
    class Result:
        def all(self): return []
    class Session:
        def scalars(self, query): return Result()
        def execute(self, query): raise AssertionError("ETF snapshots must not be checked")
    result = freshness._tracked_fundamentals_freshness(Session(), datetime(2026, 10, 4, tzinfo=UTC))
    assert result.status == "fresh"
    assert result.metadata["not_applicable"]
