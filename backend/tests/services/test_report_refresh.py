from dataclasses import replace
from datetime import date

from app.data_sources.provider_guard import retry_seconds
from app.repositories.fundamentals import FundamentalSnapshotWrite
from app.services.filing_events import parse_daily_index
from app.services.report_refresh import content_revision, merge_history
from app.workers.tasks.refresh_report_data import retry_delay


def test_partial_history_preserves_periods_but_clears_invalid_growth():
    old = [{"fiscal_period": "2026 Q1", "eps": 1, "growth_yoy_pct": 30}, {"fiscal_period": "2025 Q4", "eps": 2}]
    new = [{"fiscal_period": "2026 Q1", "eps": -1, "growth_yoy_pct": None}]
    merged = merge_history(old, new)
    assert len(merged) == 2
    assert merged[0]["eps"] == -1
    assert merged[0]["growth_yoy_pct"] is None


def test_checks_do_not_invalidate_content_but_actual_values_do():
    row = FundamentalSnapshotWrite("TEST", date(2026, 9, 1), beta=1.2, metadata_json={"report_refresh": {"checked_at": "yesterday"}})
    checked = replace(row, as_of=date(2026, 9, 14), metadata_json={"report_refresh": {"checked_at": "today"}})
    assert content_revision(row) == content_revision(checked)
    assert content_revision(row) != content_revision(replace(row, beta=1.3))


def test_filing_discovery_filters_and_deduplicates():
    text = "\n".join([
        "CIK|Company Name|Form Type|Date Filed|Filename",
        "123|Test|10-Q|2026-09-11|edgar/data/123/0001.txt",
        "123|Test|10-Q/A|2026-09-12|edgar/data/123/0002.txt",
        "123|Test|4|2026-09-13|edgar/data/123/0003.txt",
        "999|Other|10-K|2026-09-13|edgar/data/999/0004.txt",
    ])
    requests = parse_daily_index(text, {"0000000123": ["TEST"]})
    assert len(requests) == 1
    assert requests[0].payload["form"] == "10-Q/A"
    assert requests[0].payload["event_date"] == "2026-09-12"
    assert "0002" in requests[0].revision


def test_backoff_is_bounded_and_honors_retry_after():
    assert retry_seconds("120") == 120
    assert retry_seconds("bad") == 900
    assert retry_seconds("999999") == 86400
    assert retry_delay(1).total_seconds() == 7200
    assert retry_delay(100).days == 7
