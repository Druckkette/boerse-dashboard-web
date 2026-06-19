from __future__ import annotations

from datetime import date

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
                date(2026, 6, 16),
                date(2026, 6, 16),
                date(2026, 6, 16),
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
    monkeypatch.setattr(freshness.job_repository, "list_jobs", lambda limit=80: [])
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
