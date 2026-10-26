"""Real frozen OHLC, real detector/service/router, isolated settings and job state."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from app.domain.chart_patterns import PatternParameters, detect_patterns
from app.services import chart_analysis as service
from tests.helpers.chart_pattern_data import historical_bars, historical_cases


data = {case["ticker"]: historical_bars(case) for case in historical_cases()}
store = {}


def reset():
    store.clear()
    scan()


def scan():
    p = PatternParameters.model_validate(store.get(service.CONFIG_KEY, {}))
    patterns = [
        {**v.model_dump(), "name": ticker, "price_as_of": str(bars[-1].date)}
        for ticker, bars in data.items()
        for v in detect_patterns(ticker, bars, p)
    ]
    store[service.RESULT_KEY] = dict(
        generated_at="2026-10-26T10:00:00+00:00",
        parameter_hash=p.fingerprint,
        scanned_count=len(data),
        analysed_count=len(data),
        skipped_count=0,
        skipped=[],
        patterns=patterns,
    )
    return {"ok": True, "records_seen": len(data), "records_written": len(patterns)}


def install():
    original_read, original_write = (
        service.repository._read_json_setting,
        service.repository._write_json_setting,
    )
    service.repository._read_json_setting = lambda key: (
        deepcopy(store.get(key, {}))
        if key in {service.CONFIG_KEY, service.RESULT_KEY}
        else original_read(key)
    )

    def write(key, value, **kw):
        if key not in {service.CONFIG_KEY, service.RESULT_KEY}:
            return original_write(key, value, **kw)
        store[key] = deepcopy(value)
        return value

    service.repository._write_json_setting = write
    service.list_price_bars = lambda ticker, **kw: [
        SimpleNamespace(**b.__dict__) for b in data.get(ticker, [])
    ]
    service.completed_ticker_market_session = lambda ticker: SimpleNamespace(
        date=data[ticker][-1].date if ticker in data else date(2026, 10, 23)
    )
    reset()
