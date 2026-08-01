from __future__ import annotations

from datetime import UTC, date, datetime

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
