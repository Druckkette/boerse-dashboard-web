from datetime import datetime

import pytest

from app.workers.tasks import refresh_market_indices as task


@pytest.mark.parametrize(("instant", "due"), [
    ("2026-10-22T13:35:00+00:00", True),
    ("2026-10-22T20:30:00+00:00", True),
    ("2026-10-22T22:01:00+00:00", False),
    ("2026-10-22T11:00:00+00:00", False),
    ("2026-10-24T15:00:00+00:00", False),
    ("2026-11-26T16:00:00+00:00", False),
    ("2026-11-27T18:30:00+00:00", True),
    ("2026-11-27T20:01:00+00:00", False),
    ("2026-11-03T14:35:00+00:00", True),
])
def test_refresh_respects_exchange_session_dst_holidays_and_early_close(instant, due):
    assert task.index_refresh_due(datetime.fromisoformat(instant)) is due


def test_index_refresh_is_small_and_never_refreshes_portfolio_helpers(monkeypatch):
    monkeypatch.setattr(task, "index_refresh_due", lambda now: True)
    seen = []
    monkeypatch.setattr(task.refresh_prices, "run", lambda *, payload: seen.append(payload) or {"ok": True})
    assert task.refresh_market_indices.run() == {"ok": True}
    assert set(seen[0]["tickers"]) == {"^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"}
    assert seen[0]["include_market_helpers"] is False
    assert seen[0]["incremental"] is True
    assert seen[0]["price_overlap_days"] >= 1


def test_no_provider_request_outside_session_window(monkeypatch):
    monkeypatch.setattr(task, "index_refresh_due", lambda now: False)
    monkeypatch.setattr(task.refresh_prices, "run", lambda **kw: pytest.fail("Provider called outside window"))
    assert task.refresh_market_indices.run()["skipped"] is True


def test_index_refresh_does_not_queue_behind_full_universe():
    from app.workers.celery_app import celery_app
    from app.workers.scheduler import get_beat_schedule

    job = get_beat_schedule()["market-indices-five-minutes"]
    assert job["task"] == "refresh_market_indices"
    assert job["schedule"] == 300
    assert job["options"]["expires"] < 300
    assert celery_app.amqp.router.route({}, "refresh_market_indices", (), {})["queue"].name == "interactive"
