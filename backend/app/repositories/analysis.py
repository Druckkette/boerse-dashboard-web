"""Bounded projections for analysis; no provider calls and no writes."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import SessionLocal
from app.db.models import CashFlow, Instrument, Transaction
from app.repositories.portfolio import PortfolioRepositoryUnavailable


def ledger() -> dict:
    try:
        with SessionLocal() as db:
            instruments = {row.id: row for row in db.scalars(select(Instrument).where(Instrument.id.in_(select(Transaction.instrument_id)))).all()}
            transactions = list(db.scalars(select(Transaction).order_by(Transaction.date, Transaction.created_at, Transaction.id)).all())
            events = []
            for tx in transactions:
                instrument = instruments.get(tx.instrument_id)
                raw = tx.raw_json or {}
                net = float(tx.net_amount or 0)
                if raw.get("source") != "trade_republic_transactions":
                    net = -abs(net) if tx.transaction_type == "buy" else net
                events.append(dict(id=tx.id, ticker=tx.ticker, date=tx.date, kind=tx.transaction_type,
                    shares=tx.shares, price=tx.price, net=net, fees=abs(tx.fees or 0), tax=abs(tx.tax or 0),
                    currency=tx.currency, raw=raw, name=instrument.name if instrument else tx.ticker,
                    asset_class=instrument.asset_class if instrument else str(raw.get("asset_class") or "")))
            cash = [dict(date=row.date, amount=float(row.amount), currency=row.currency, kind=row.flow_type)
                    for row in db.scalars(select(CashFlow).order_by(CashFlow.date, CashFlow.id)).all()]
            return {"events": events, "cash_flows": cash}
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable("Bewertungshistorie derzeit nicht verfügbar.") from exc


def price_currency_metadata(tickers: list[str]) -> dict:
    try:
        with SessionLocal() as db:
            instruments = list(db.scalars(select(Instrument).where(Instrument.ticker.in_(tickers))).all())
            return {row.ticker: {"name": row.name, "metadata": row.metadata_json or {}, "currency": row.currency} for row in instruments}
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable("Wertpapierstammdaten derzeit nicht verfügbar.") from exc
