"""Append-only, deduplicated evidence; no retention expiry or product foreign key."""
from datetime import UTC, date, datetime
import gzip
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import PortfolioPriceArchive
from app.db.session import SessionLocal
from app.repositories import prices


def encode_payload(payload: dict) -> tuple[str, bytes]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest(), gzip.compress(raw, mtime=0)


def decode_payload(row: PortfolioPriceArchive) -> dict:
    raw = gzip.decompress(row.payload_gzip)
    if hashlib.sha256(raw).hexdigest() != row.sha256:
        raise ValueError("Portfolio price archive checksum mismatch")
    return json.loads(raw)


def append_evidence(key: str, kind: str, payload: dict, *, source: str,
                    source_url: str = "", price_date: date | None = None,
                    observed_at: datetime | None = None) -> dict:
    digest, compressed = encode_payload(payload)
    return dict(id=str(uuid4()), instrument_key=key.upper(), kind=kind, source=source,
        source_url=source_url, price_date=price_date, observed_at=observed_at or datetime.now(UTC),
        sha256=digest, payload_gzip=compressed)


def save_evidence(items: list[dict]) -> int:
    count = 0
    with SessionLocal() as db:
        for offset in range(0, len(items), 500):
            statement = insert(PortfolioPriceArchive).values(items[offset:offset + 500]).on_conflict_do_nothing(
                constraint="uq_portfolio_price_archive").returning(PortfolioPriceArchive.id)
            count += len(db.scalars(statement).all())
        db.commit()
    return count


def archive_cached_inputs(tickers: set[str]) -> int:
    """Preserve every cached date, not just today's quote or the current year."""
    metadata = prices.list_instrument_metadata(tickers)
    bars = prices.list_price_bars_for_tickers(tickers)
    items = []
    for key, values in metadata.items():
        stable = {name: values[name] for name in (
            "stock_splits", "stock_splits_source", "fixed_redemption", "issuer_history_source", "issuer_final_bid"
        ) if name in values}
        if stable:
            checked = values.get("issuer_checked_at") or values.get("price_checked_at")
            items.append(append_evidence(key, "instrument_metadata", stable, source="database",
                observed_at=datetime.fromisoformat(checked) if checked else None))
    for key, rows in bars.items():
        for row in rows:
            if row.close is None:
                continue
            payload = {field: getattr(row, field, None) for field in (
                "open", "high", "low", "close", "adj_close", "volume", "split_adjustment_factor")}
            payload.update(date=row.date.isoformat(), source=row.source)
            if row.source == "yfinance" and row.split_adjustment_factor is None:
                # Legacy split restoration depends on the download vintage.
                # Never turn such a quote into a freshly downloaded quote.
                payload["legacy_fetched_at"] = row.fetched_at.isoformat() if row.fetched_at else None
            # Keep distinct retrievals, including a correction that returns to
            # an earlier price. Re-archiving the same retrieval is idempotent.
            items.append(append_evidence(key, "price_bar", payload, source=row.source,
                price_date=row.date, observed_at=row.fetched_at or row.created_at))
    return save_evidence(items)


def restore_cached_inputs(tickers: set[str]) -> int:
    """Explicit recovery from the local archive, without any external provider."""
    with SessionLocal() as db:
        rows = list(db.scalars(select(PortfolioPriceArchive).where(
            PortfolioPriceArchive.instrument_key.in_(tickers),
            PortfolioPriceArchive.kind.in_(["price_bar", "instrument_metadata"])
        ).order_by(PortfolioPriceArchive.observed_at, PortfolioPriceArchive.created_at)))
    latest = {}
    metadata = {}
    for row in rows:
        payload = decode_payload(row)
        if row.kind == "instrument_metadata":
            metadata[row.instrument_key] = payload
        else:
            latest[(row.instrument_key, row.source, row.price_date)] = (payload, row.observed_at)
    grouped = {}
    for (key, source, _), (payload, observed_at) in latest.items():
        values = {**payload, "date": date.fromisoformat(payload["date"])}
        values.pop("source")
        values.pop("legacy_fetched_at", None)
        grouped.setdefault((key, source), []).append(prices.PriceBarWrite(**values))
    count = sum(prices.upsert_price_bars(key, bars, source=source) for (key, source), bars in grouped.items())
    with SessionLocal() as db:
        for key, rows in prices.list_price_bars_for_tickers(tickers).items():
            for bar in rows:
                identity = (key, bar.source, bar.date)
                if identity in latest:
                    payload, observed_at = latest[identity]
                    db.merge(bar).fetched_at = (
                        datetime.fromisoformat(payload["legacy_fetched_at"]) if payload.get("legacy_fetched_at")
                        else None if "legacy_fetched_at" in payload else observed_at)
        db.commit()
    for key, values in metadata.items():
        prices.save_instrument_metadata(key, values, create_issuer="fixed_redemption" in values or "issuer_history_source" in values)
    return count
