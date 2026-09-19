"""Current operating data health, independent of historical diagnostic findings."""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import BreadthDaily, Instrument, MarketSnapshot, Position, PriceBar
from app.db.session import SessionLocal
from app.services.market_calendar import completed_us_market_session, price_is_current


def summarize_sources(sources: list[dict], *, now: datetime) -> dict:
    reasons = [source for source in sources if source["required"] and source["status"] != "fresh"]
    status = "blocked" if any(s["status"] in {"missing", "error"} for s in reasons) else "limited" if reasons else "trusted"
    return {"decision_status": status, "generated_at": now.isoformat(), "reasons": reasons,
            "sources": sources, "summary": "; ".join(s["detail"] for s in reasons) if reasons else
            "Relevante Betriebsdaten sind verfügbar und ausreichend aktuell."}


def get_system_quality() -> dict:
    now = datetime.now(UTC)
    completed = completed_us_market_session(now)
    try:
        with SessionLocal() as db:
            tickers = set(db.scalars(select(Position.ticker).where(Position.is_open.is_(True))))
            wanted = tickers | {"^GSPC", "SPY"}
            rows = db.execute(select(Instrument.ticker, PriceBar.date, PriceBar.fetched_at)
                .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                .where(Instrument.ticker.in_(wanted), PriceBar.close.is_not(None))
                .distinct(Instrument.ticker)
                .order_by(Instrument.ticker, PriceBar.date.desc(), PriceBar.fetched_at.desc().nulls_last())).all()
            prices = {ticker: (day, fetched) for ticker, day, fetched in rows}
            snapshot_date = db.scalar(select(func.max(MarketSnapshot.date)))
            breadth_date = db.scalar(select(func.max(BreadthDaily.date)))
        sources = []
        for ticker in sorted(tickers | {"^GSPC"}):
            latest = prices.get(ticker) or (prices.get("SPY") if ticker == "^GSPC" else None)
            # Intraday quotes are expected for holdings; daily market products need only a completed session.
            fresh = latest and (price_is_current(*latest, now=now) if ticker in tickers else latest[0] >= completed.date)
            status = "fresh" if fresh else "stale" if latest else "missing"
            sources.append({"name": f"price:{ticker}", "required": True, "status": status,
                            "as_of": latest[0].isoformat() if latest else None,
                            "detail": f"{ticker}: Kursdaten {'veraltet' if latest else 'fehlen'}" if not fresh else f"{ticker}: aktuell"})
        for name, day in (("market_snapshot", snapshot_date), ("market_breadth", breadth_date)):
            status = "fresh" if day and day >= completed.date else "stale" if day else "missing"
            sources.append({"name": name, "required": True, "status": status,
                            "as_of": day.isoformat() if day else None,
                            "detail": f"{name}: {status} (erwartet {completed.date.isoformat()})"})
        # 13F, quarterly fundamentals, missing personal stops and old split candidates
        # remain in detailed diagnostics; they are not outages of the normal dashboard.
        return summarize_sources(sources, now=now)
    except SQLAlchemyError:
        return summarize_sources([{"name": "database", "required": True, "status": "error",
                                   "detail": "Zentrale Datenbank nicht erreichbar."}], now=now)
