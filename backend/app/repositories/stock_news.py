"""Durable news cache and rolling budget in existing Postgres AppSetting rows.

One physical connection owns the per-symbol session advisory lock across commits.
Quota reservations commit on that SAME connection before contacting Marketaux.
No second pooled connection is required while a lock is held.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import AppSetting, Instrument, UniverseSymbolMapping
from app.db.session import SessionLocal, engine


NAMESPACE = 7341507
BUDGET_KEY = "marketaux:budget:v1"


class NewsRepositoryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SymbolIdentity:
    ticker: str
    symbol: str
    name: str
    exchange: str
    us_listing: bool = False


def foreign_listing_country(symbol: str) -> str | None:
    """Recognized qualified provider symbols, not a blanket suffix removal."""
    suffix = symbol.rsplit(".", 1)[1].upper() if "." in symbol else ""
    return {
        "DE": "de", "HK": "hk", "L": "gb", "TO": "ca", "V": "ca", "AX": "au",
        "PA": "fr", "MI": "it", "MC": "es", "AS": "nl", "BR": "be", "ST": "se",
        "OL": "no", "CO": "dk", "HE": "fi", "SW": "ch", "T": "jp", "TW": "tw",
        "TWO": "tw", "KS": "kr", "KQ": "kr", "SI": "sg", "NS": "in", "BO": "in",
        "SA": "br", "MX": "mx", "JO": "za",
    }.get(suffix)


def resolve_symbol(ticker: str) -> SymbolIdentity | None:
    try:
        with SessionLocal() as db:
            instrument = db.scalars(select(Instrument).where(Instrument.ticker == ticker)).first()
            if instrument is None:
                return None
            mapping = db.scalars(select(UniverseSymbolMapping).where(
                UniverseSymbolMapping.universe_key == "us_common_stocks",
                UniverseSymbolMapping.source_ticker == ticker,
                UniverseSymbolMapping.status == "active",
            )).first()
            metadata = instrument.metadata_json or {}
            # Dedicated Marketaux metadata is optional; otherwise reuse the stored
            # provider mapping without stripping a foreign exchange suffix.
            symbol = (metadata.get("marketaux_symbol")
                      or (mapping.yahoo_symbol if mapping else None)
                      or instrument.yahoo_symbol or ticker)
            listing = metadata.get("nasdaq_listing") or {}
            exchange = str(instrument.exchange or listing.get("exchange") or "")
            symbol = str(symbol).strip().upper()
            us_listing = (bool(listing) or exchange.upper() in {
                                      "NASDAQ", "NYSE", "NYSE ARCA", "AMEX", "BATS", "NMS", "NYQ",
                                  }) and foreign_listing_country(symbol) is None
            return SymbolIdentity(ticker, symbol, instrument.name or ticker, exchange, us_listing)
    except SQLAlchemyError:
        raise NewsRepositoryUnavailable() from None


def _date(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, TypeError, OverflowError):
        return None


class NewsStore:
    def __init__(self, db: Session):
        self.db = db

    def read(self, key: str) -> dict:
        row = self.db.get(AppSetting, key, populate_existing=True)
        return deepcopy(row.value_json if row else {})

    def write(self, key: str, value: dict) -> None:
        row = self.db.get(AppSetting, key, populate_existing=True)
        if row is None:
            row = AppSetting(key=key, description="Marketaux company news cache/budget")
            self.db.add(row)
        row.value_json = deepcopy(value)
        self.db.commit()

    def reserve(self, *, limit: int, credential_id: str) -> tuple[bool, str]:
        self.db.execute(text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:key))"),
                        {"namespace": NAMESPACE, "key": BUDGET_KEY})
        now = self.db.scalar(text("SELECT clock_timestamp()"))
        row = self.read(BUDGET_KEY)
        attempts = [stamp for stamp in row.get("attempts", [])
                    if (parsed := _date(stamp)) is not None and parsed > now - timedelta(days=1)]
        blocked = _date(row.get("blocked_until"))
        if blocked and blocked > now and row.get("credential_id") == credential_id:
            self.db.commit()
            return False, row.get("reason", "unavailable")
        if len(attempts) >= limit:
            self.db.commit()
            return False, "limit_reached"
        attempts.append(now.isoformat())
        self.write(BUDGET_KEY, {"attempts": attempts})
        return True, "ok"

    def block(self, *, reason: str, seconds: int, credential_id: str) -> None:
        self.db.execute(text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:key))"),
                        {"namespace": NAMESPACE, "key": BUDGET_KEY})
        now = self.db.scalar(text("SELECT clock_timestamp()"))
        value = self.read(BUDGET_KEY)
        value.update(reason=reason, blocked_until=(now + timedelta(seconds=seconds)).isoformat(),
                     credential_id=credential_id)
        self.write(BUDGET_KEY, value)


@contextmanager
def locked_store(cache_key: str, *, wait_seconds: int = 20):
    try:
        with engine.connect() as connection:
            with Session(bind=connection, expire_on_commit=False) as db:
                acquired = False
                try:
                    db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"),
                               {"timeout": f"{wait_seconds * 1000}ms"})
                    db.execute(text("SELECT pg_advisory_lock(:namespace, hashtext(:key))"),
                               {"namespace": NAMESPACE, "key": cache_key})
                    acquired = True
                    db.commit()
                    yield NewsStore(db)
                finally:
                    db.rollback()
                    if acquired:
                        db.execute(text("SELECT pg_advisory_unlock(:namespace, hashtext(:key))"),
                                   {"namespace": NAMESPACE, "key": cache_key})
                        db.commit()
    except SQLAlchemyError:
        raise NewsRepositoryUnavailable() from None
