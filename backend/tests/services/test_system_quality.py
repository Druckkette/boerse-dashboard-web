from datetime import UTC, datetime

from app.services.system_quality import summarize_sources
from app.services.market_calendar import completed_us_market_session

NOW = datetime(2026, 9, 19, 12, tzinfo=UTC)


def source(status, required=True, name="prices"):
    return {"name": name, "status": status, "required": required, "detail": status}


def test_current_and_optional_sources():
    assert summarize_sources([source("fresh"), source("missing", False, "13f")], now=NOW)["decision_status"] == "trusted"
    assert summarize_sources([source("stale")], now=NOW)["decision_status"] == "limited"
    assert summarize_sources([source("missing")], now=NOW)["decision_status"] == "blocked"


def test_recovery_does_not_latch_old_errors():
    assert summarize_sources([source("error")], now=NOW)["decision_status"] == "blocked"
    result = summarize_sources([source("fresh")], now=NOW)
    assert result["decision_status"] == "trusted"
    assert result["reasons"] == []


def test_closed_market_and_daily_vs_intraday_products():
    assert completed_us_market_session(NOW).date.isoformat() == "2026-09-18"
    assert completed_us_market_session(datetime(2026, 9, 18, 15, tzinfo=UTC)).date.isoformat() == "2026-09-17"
    # Different cadence is evaluated per source; quarterly diagnostics are not daily outages.
    assert summarize_sources([source("fresh"), source("stale", False, "quarterly_fundamentals")], now=NOW)["decision_status"] == "trusted"
