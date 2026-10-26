"""Fresh source validation and cache preservation for targeted chart repairs."""

from dataclasses import replace
from types import SimpleNamespace

from billiard.exceptions import SoftTimeLimitExceeded
import pytest

from app.data_sources.yfinance_client import FetchedPriceBar
from app.services import chart_price_repair as service
from tests.domain.test_chart_patterns import series


@pytest.fixture
def setup(monkeypatch):
    bars = [FetchedPriceBar(**b.__dict__, adj_close=b.close) for b in series([100] * 50)]
    writes, calls = [], []
    monkeypatch.setattr(service, "list_price_bars", lambda *a, **kw: list(bars))

    def fetch(symbol, **kwargs):
        calls.append((symbol, kwargs))
        return list(bars)

    monkeypatch.setattr(service, "fetch_daily_price_bars", fetch)
    monkeypatch.setattr(
        service, "upsert_price_bars", lambda *a, **kw: writes.append((a, kw)) or len(a[1])
    )

    def run(ticker="TEST", symbol=None):
        return service.repair_chart_history(
            ticker, symbol, start_date=bars[0].date, end_date=bars[-1].date
        )

    return SimpleNamespace(bars=bars, calls=calls, writes=writes, run=run)


def test_valid_complete_refresh_writes_without_price_conversion(setup):
    setup.bars[20] = replace(setup.bars[20], stock_split=2, split_adjustment_factor=0.5)
    result = setup.run()
    assert result["ok"] and result["records_written"] == 50
    assert result["split_events"] == {setup.bars[20].date.isoformat(): 2}
    written = setup.writes[0][0][1][20]
    assert written.close == 100 and written.split_adjustment_factor == 0.5
    assert len(setup.calls) == 1 and setup.calls[0][1]["timeout"] == 10


@pytest.mark.parametrize(
    "field,value",
    [("open", None), ("high", 90), ("low", 110), ("close", float("inf")), ("volume", -1)],
)
def test_invalid_fresh_quotes_leave_cache_unchanged(setup, field, value):
    setup.bars[20] = replace(setup.bars[20], **{field: value})
    result = setup.run()
    assert not result["ok"] and result["invalid_records"] == 1
    assert not setup.writes


def test_empty_truncated_and_sparse_histories_never_replace_old_basis(setup, monkeypatch):
    for fetched in [[], setup.bars[-24:], setup.bars[25:], setup.bars[::2]]:
        monkeypatch.setattr(service, "fetch_daily_price_bars", lambda *a, **kw: fetched)
        result = setup.run()
        assert not result["ok"] and not setup.writes


def test_duplicate_fresh_dates_are_not_silently_deduplicated(setup):
    setup.bars.append(setup.bars[-1])
    result = setup.run()
    assert result["invalid_records"] == 1 and not setup.writes


def test_persisting_jump_is_reported_without_adjusting_prices(setup):
    setup.bars[25:] = [replace(b, open=200, high=201, low=199, close=200) for b in setup.bars[25:]]
    result = setup.run()
    assert not result["ok"] and result["fresh_jump_verified"]
    assert result["records_written"] == 50
    assert setup.writes[0][0][1][25].close == 200


def test_provider_error_rate_limit_and_worker_interrupt_are_distinct(setup, monkeypatch):
    for exc, code in [
        (RuntimeError("private-token=never-return"), "provider_error"),
        (RuntimeError("429 Too Many Requests"), "rate_limited"),
    ]:

        def fail(*a, **kw):
            raise exc

        monkeypatch.setattr(service, "fetch_daily_price_bars", fail)
        result = setup.run()
        assert result["reason_code"] == code and "private-token" not in str(result)
        assert not setup.writes

    def interrupted(*a, **kw):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(service, "fetch_daily_price_bars", interrupted)
    with pytest.raises(SoftTimeLimitExceeded):
        setup.run()


def test_hong_kong_alias_preserves_explicit_different_mapping(setup):
    setup.run("2318-HK", "2318-HK")
    assert setup.calls[-1][0] == "2318.HK"
    setup.run("2318-HK", "9999.HK")
    assert setup.calls[-1][0] == "9999.HK"


def test_repository_failure_propagates_instead_of_becoming_provider_failure(setup, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(service, "upsert_price_bars", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        setup.run()
