"""Real Postgres roundtrip, fresh sessions, and atomic scan publication."""

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting
from app.domain.chart_patterns import PatternParameters
from app.repositories import prices, settings
from app.services import chart_analysis as service
from app.workers.tasks.common import JobCancelled
from tests.domain.test_chart_patterns import fixture


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured"
)


def test_chart_settings_price_scan_and_cancellation_roundtrip(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests", "Never run writes on a user database"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    for module in [service, prices, settings]:
        monkeypatch.setattr(module, "SessionLocal", sessions)
    with sessions() as db:
        db.execute(
            delete(AppSetting).where(AppSetting.key.in_([service.CONFIG_KEY, service.RESULT_KEY]))
        )
        db.commit()
    ticker = "CHART" + uuid4().hex[:8].upper()
    bars = fixture()
    shift = timedelta(days=((date.today() - bars[-1].date).days - 30) // 7 * 7)
    prices.upsert_price_bars(
        ticker,
        [
            prices.PriceBarWrite(b.date + shift, b.open, b.high, b.low, b.close, b.close, b.volume)
            for b in bars
        ],
    )
    p = PatternParameters()
    service.save_config(p)
    assert service.get_config()["parameter_hash"] == p.fingerprint
    progress = []
    result = service.scan_universe(progress=lambda done, total: progress.append((done, total)))
    assert result["ok"]
    assert progress[-1][0] == progress[-1][1]
    rows = service.get_results(search=ticker)["rows"]
    assert any(row["kind"] == "cup_with_handle" for row in rows)
    chart = service.analyse(ticker)
    assert any(row["kind"] == "cup_with_handle" for row in chart["patterns"])
    before = settings._read_json_setting(service.RESULT_KEY)

    def cancel():
        raise JobCancelled("test")

    with pytest.raises(JobCancelled):
        service.scan_universe(cancelled=cancel)
    assert settings._read_json_setting(service.RESULT_KEY) == before
    service.save_config(PatternParameters(cup_max_depth_pct=25))
    assert service.get_results(search=ticker)["obsolete"]
    assert not any(p["kind"].startswith("cup") for p in service.analyse(ticker)["patterns"])
    engine.dispose()
