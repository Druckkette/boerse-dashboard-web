import pytest

from app.workers.tasks.smart_refresh_market_data import _action_requires_continuation


def completed():
    return {"ok": True, "partial": True, "universe_count": 5593, "records_seen": 5593, "error_count": 0, "missing_count": 107}


def test_screened_universe_with_missing_prices_is_complete():
    assert not _action_requires_continuation("refresh_stock_assessments", completed())


@pytest.mark.parametrize("change", [{"records_seen": 100}, {"error_count": 1}, {"stopped_due_to_timeout": True}])
def test_unfinished_or_failed_screening_still_requires_continuation(change):
    assert _action_requires_continuation("refresh_stock_assessments", {**completed(), **change})


def test_partial_data_refreshes_are_not_misclassified_as_complete():
    assert _action_requires_continuation("refresh_prices", completed())
    assert _action_requires_continuation("refresh_stock_assessments", {"partial": True})
    assert not _action_requires_continuation("refresh_stock_assessments", None)
