"""Recovery must work after the online product and mutable cache are gone."""
from datetime import UTC, date, datetime
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import Instrument, PortfolioPriceArchive, PriceBar
from app.repositories import prices, portfolio_price_archive as archive

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")


@pytest.fixture
def database(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(prices, "SessionLocal", sessions)
    monkeypatch.setattr(archive, "SessionLocal", sessions)
    yield sessions, "ARC" + uuid4().hex[:10].upper()
    engine.dispose()


def test_archive_is_idempotent_retains_corrections_and_restores_cache_without_provider(database):
    sessions, key = database
    first = prices.PriceBarWrite(date(2026, 10, 15), None, None, None, 2.0, None, None)
    prices.upsert_price_bars(key, [first], source="vontobel:EUR:bid")
    evidence = {"amount": 2.1, "currency": "EUR", "valuation_date": "2026-10-16", "source_url": "https://issuer.example/terms"}
    prices.save_instrument_metadata(key, {"fixed_redemption": evidence})
    assert archive.archive_cached_inputs({key}) == 2
    prices.upsert_price_bars(key, [first], source="vontobel:EUR:bid")
    assert archive.archive_cached_inputs({key}) == 0
    corrected = prices.PriceBarWrite(first.date, None, None, None, 2.05, None, None)
    prices.upsert_price_bars(key, [corrected], source="vontobel:EUR:bid")
    assert archive.archive_cached_inputs({key}) == 1
    with sessions() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == key))
        db.execute(delete(PriceBar).where(PriceBar.instrument_id == instrument.id))
        instrument.metadata_json = {}
        db.commit()
    assert prices.list_price_bars(key) == []
    assert archive.restore_cached_inputs({key}) == 1
    assert prices.list_price_bars(key)[0].close == 2.05
    assert prices.list_instrument_metadata([key])[key]["fixed_redemption"] == evidence
    with sessions() as db:
        observations = list(db.scalars(select(PortfolioPriceArchive).where(PortfolioPriceArchive.instrument_key == key)))
    assert sorted(archive.decode_payload(row)["close"] for row in observations if row.kind == "price_bar") == [2.0, 2.05]


def test_issuer_response_evidence_survives_loss_of_instrument(database):
    sessions, key = database
    item = archive.append_evidence(key, "issuer_response", {"isin": key, "currency": "EUR", "bid": 0.001}, source="hsbc:EUR:bid", source_url="https://issuer.example/quote")
    assert archive.save_evidence([item]) == 1
    assert archive.save_evidence([archive.append_evidence(key, "issuer_response", {"bid": 0.001, "currency": "EUR", "isin": key}, source="hsbc:EUR:bid")]) == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(PortfolioPriceArchive).where(PortfolioPriceArchive.instrument_key == key)) == 1
        row = db.scalar(select(PortfolioPriceArchive).where(PortfolioPriceArchive.instrument_key == key))
        assert archive.decode_payload(row)["bid"] == 0.001
        row.sha256 = "0" * 64
        db.commit()
    with pytest.raises(ValueError, match="checksum"):
        archive.decode_payload(row)


def test_archive_preserves_split_basis_and_prices_from_closed_prior_years(database):
    _, key = database
    prices.upsert_price_bars(key, [prices.PriceBarWrite(date(2025, 1, 2), None, None, None, 10, None, None, split_adjustment_factor=10)])
    assert archive.archive_cached_inputs({key}) == 1
    assert archive.restore_cached_inputs({key}) == 1
    assert prices.list_price_bars(key)[0].split_adjustment_factor == 10


def test_legacy_download_vintage_is_not_changed_by_archive_recovery(database):
    sessions, key = database
    prices.upsert_price_bars(key, [prices.PriceBarWrite(date(2026, 4, 10), None, None, None, 100, None, None)])
    before_split = datetime(2026, 4, 11, tzinfo=UTC)
    with sessions() as db:
        row = db.scalar(select(PriceBar).join(Instrument).where(Instrument.ticker == key))
        row.fetched_at = before_split
        db.commit()
    archive.archive_cached_inputs({key})
    archive.restore_cached_inputs({key})
    assert prices.list_price_bars(key)[0].fetched_at == before_split
