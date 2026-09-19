"""Assemble existing application data. Never refresh prices or persist sell decisions."""
from dataclasses import asdict, replace
from datetime import UTC, datetime
import logging

from sqlalchemy import or_, select

from app.db.models import Instrument, MarketSnapshot, TradeJournalEntry
from app.db.session import SessionLocal
from app.domain.sell.service import preview_position_sell_decision
from app.repositories import portfolio, sell_state
from app.reports.model import InvestmentReport, ReportSection
from app.services.fx import cached_currency_usd_factor
from app.services.portfolio import get_buy_strength_assessment
from app.services.prices import get_price_history
from app.services.relative_strength import get_relative_strength_for_ticker
from app.services.sec13f import get_institutional_13f_for_ticker
from app.services.stocks import get_stock_assessment
from app.services.trade_journal import _detail_from_row

logger = logging.getLogger(__name__)


def collect_report(ticker: str, trade_id: str | None = None) -> InvestmentReport:
    ticker = ticker.strip().upper()
    notices: list[str] = []
    sections: list[ReportSection] = []
    with SessionLocal() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
        selected = db.get(TradeJournalEntry, trade_id) if trade_id else None
        if trade_id and (selected is None or selected.ticker != ticker):
            raise LookupError("Trade nicht gefunden oder einer anderen Aktie zugeordnet.")
        query = select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker)
        if selected:
            # Only this trade and explicitly linked entries, never unrelated ticker history.
            root_id = selected.linked_entry_id or selected.id
            query = query.where(or_(TradeJournalEntry.id == selected.id,
                                    TradeJournalEntry.id == root_id,
                                    TradeJournalEntry.linked_entry_id == root_id))
        journal = [_detail_from_row(row).model_dump(mode="json") for row in db.scalars(
            query.order_by(TradeJournalEntry.trade_date, TradeJournalEntry.created_at)
        )]
        if instrument is None and not journal:
            raise LookupError("Keine gespeicherten Daten für diese Aktie vorhanden.")
        name = instrument.name if instrument else ticker
        currency = instrument.currency if instrument else ""
        isin = instrument.isin if instrument else ""
        market = db.scalar(select(MarketSnapshot).order_by(MarketSnapshot.date.desc()).limit(1))
        market_data = ({"as_of": market.date.isoformat(), "ampel_phase": market.ampel_phase,
                        "warning_count": market.warning_count, "breadth_mode": market.breadth_mode,
                        "volatility_regime": market.volatility_regime, **(market.metrics_json or {})}
                       if market else {})

    def optional(title, loader):
        try:
            result = loader()
            return result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        except Exception:
            logger.exception("PDF data source unavailable: %s / %s", ticker, title)
            notices.append(f"{title}: Daten konnten nicht geladen werden.")
            return {}

    if selected:
        entry = next(item for item in journal if item["id"] == trade_id)
        snapshot = entry["stock_snapshot"]
        assessment = snapshot.get("assessment", snapshot)
        prices = snapshot.get("price_history", {})
        sections.append(ReportSection("Position zum Trade-Zeitpunkt", entry["portfolio_snapshot"]))
        sections.append(ReportSection("Marktumfeld zum Trade-Zeitpunkt", entry["market_snapshot"]))
        for key, title in [("fundamentals", "Fundamentaldaten"),
                           ("institutional_13f", "Institutionelle Anleger / 13F"),
                           ("relative_strength", "Relative Stärke")]:
            if snapshot.get(key):
                sections.append(ReportSection(title, snapshot[key]))
        notices.append("Historischer Report: Bewertungen und Kurse stammen aus dem gespeicherten "
                       "Trade-Snapshot. Unternehmensstammdaten entsprechen dem heutigen Stand.")
    else:
        assessment = optional("Aktienbewertung", lambda: get_stock_assessment(ticker))
        prices = optional("Kursverlauf", lambda: get_price_history(ticker))
        rows = optional("Position", portfolio.list_open_positions)
        positions = [row for row in rows if row.ticker == ticker] if rows else []
        buy_row = None
        for row in positions:
            data, buy_row = position_data(row, prices.get("currency") or currency)
            sections.append(ReportSection("Position", data))
        if positions:
            if buy_row is not None:
                sections.append(ReportSection("Kaufstärke", optional("Kaufstärke", lambda: get_buy_strength_assessment(ticker, position_row=buy_row))))
            else:
                notices.append("Kaufstärke: kein Kurs oder keine belastbare Währungsumrechnung vorhanden.")
            sections.append(ReportSection("Verkaufsentscheidung", optional("Verkaufsentscheidung", lambda: preview_position_sell_decision(ticker))))
        if assessment.get("fundamentals"):
            sections.append(ReportSection("Fundamentaldaten", assessment["fundamentals"]))
        sections.extend([
            ReportSection("Marktumfeld", market_data),
            ReportSection("Relative Stärke", optional("Relative Stärke", lambda: get_relative_strength_for_ticker(ticker))),
            ReportSection("Institutionelle Anleger / 13F", optional("13F", lambda: get_institutional_13f_for_ticker(ticker))),
        ])
        notes = optional("Verkaufsnachbetrachtung", lambda: {"notes": [
            item.model_dump(mode="json") for item in sell_state.list_post_mortem_notes(ticker)]})
        if notes.get("notes"):
            sections.append(ReportSection("Verkaufsnachbetrachtung", notes))
    if not assessment or assessment.get("source") == "missing":
        notices.append("Keine belastbare Aktienbewertung vorhanden; es wird kein Ersatzscore angezeigt.")
    return InvestmentReport(ticker=ticker, name=name or ticker, currency=currency, isin=isin,
                            trade_id=trade_id, exported_at=datetime.now(UTC), assessment=assessment,
                            prices=prices, sections=sections, journal=journal, notices=notices)


def position_data(row, quote_currency):
    """Value holdings in their stored currency using only real, current cached FX."""
    data = asdict(row)
    data["invested_amount"] = row.shares * row.entry_price
    current = row.current_price if row.current_price_source == "price_cache" else None
    factor = 1.0
    if current is not None and quote_currency != row.currency:
        source_factor = cached_currency_usd_factor(quote_currency)
        target_factor = cached_currency_usd_factor(row.currency)
        factor = source_factor / target_factor if source_factor and target_factor else None
        current = current * factor if factor else None
        data["fx_conversion"] = factor
    data["current_price"] = current
    data["market_value"] = row.shares * current if current is not None else None
    data["pnl_abs"] = row.shares * (current - row.entry_price) if current is not None else None
    data["pnl_pct"] = (current / row.entry_price - 1) * 100 if current is not None and row.entry_price else None
    stop = row.stop_price
    if stop is None and row.stop_pct is not None:
        stop = row.entry_price * (1 - row.stop_pct / 100)
        data["stop_price"] = stop
    if stop is not None and current is not None:
        data["position_loss_risk"] = max(0, current - stop) * row.shares
        data["position_loss_risk_pct"] = max(0, 1 - stop / current) * 100 if current else None
    # Buy-strength uses cached chart bars in quote currency; normalize the entry to match.
    buy_row = replace(row, entry_price=row.entry_price / factor, currency=quote_currency) if current is not None and factor else None
    return data, buy_row
