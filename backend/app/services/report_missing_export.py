"""Explain missing report inputs with one CSV row per ticker and missing field."""
from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO

from sqlalchemy import text

from app.db.session import engine
from app.repositories.fundamentals import _metadata_history, _usable_history_count


HISTORIES = {
    "eps_quarter_history": "EPS: Quartalsvergleiche",
    "annual_eps_history": "EPS: Jahresvergleiche",
    "revenue_quarter_history": "Umsatz: Quartalsvergleiche",
    "annual_revenue_history": "Umsatz: Jahresvergleiche",
}
REASONS = {
    "waiting_sec_data": "Erwartete SEC-Berichtsperiode noch nicht veröffentlicht oder strukturiert verfügbar",
    "waiting_yahoo_data": "Yahoo liefert derzeit keinen ergänzenden Wert",
    "waiting_fmp_fallback": "Optionaler FMP-Fallback noch nicht verfügbar",
    "unsupported_taxonomy": "Kein sicher zuordenbarer SEC-Finanzwert",
    "missing_history": "Zu wenige vergleichbare veröffentlichte Perioden",
    "rate_limited": "Optionaler Datenanbieter begrenzt; erneute Prüfung geplant",
    "provider_error": "Datenanbieter vorübergehend nicht erreichbar",
}
HEADERS = (
    "Ticker", "Datenbereich", "Status", "Fehlender Wert", "Vorhanden", "Benötigt",
    "Warum", "Letzte Meldung", "Letzte Prüfung (UTC)", "Nächste Prüfung (UTC)",
)


def _safe_cell(value: object) -> str:
    result = "" if value is None else str(value)
    return "'" + result if result.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else result


def _iso(value: date | datetime | None) -> str:
    return value.isoformat() if value else ""


def build_missing_rows(work_items: list[dict], snapshots: dict[str, dict],
                       price_stats: dict[str, dict]) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for item in work_items:
        ticker, group, status = item["ticker"], item["data_group"], item["status"]
        snapshot = snapshots.get(ticker) or {}
        result = item.get("result_json") or {}
        payload = item.get("payload_json") or {}
        reason_code = result.get("reason_code") or ""
        reason = REASONS.get(reason_code, "")
        message = item.get("error") or result.get("reason") or ""
        common = (ticker, group, status)
        tail = (_safe_cell(message), _iso(item.get("checked_at")), _iso(item.get("due_at")))

        def add(field: str, available: object, required: object, why: str) -> None:
            rows.append(tuple(_safe_cell(part) for part in (*common, field, available, required, why)) + tail)

        if group == "statements":
            metadata = snapshot.get("metadata_json") or {}
            if not snapshot:
                add("Fundamental-Snapshot", 0, 1, reason or "Noch keine verwertbaren Statements gespeichert")
            else:
                for key, label in HISTORIES.items():
                    count = _usable_history_count(_metadata_history(metadata, key))
                    if count < 3:
                        add(label, count, 3, reason or "Zu wenige vergleichbare veröffentlichte Perioden")
                if reason_code == "waiting_sec_data" or (
                    status == "waiting_source" and not any(
                        _usable_history_count(_metadata_history(metadata, key)) < 3 for key in HISTORIES
                    )
                ):
                    add("Erwartete Berichtsperiode", snapshot.get("fiscal_period") or "unbekannt",
                        payload.get("expected_period") or "neuer SEC-Bericht",
                        reason or "Neuer Bericht noch nicht in den strukturierten SEC-Daten")
        elif group == "beta":
            if not snapshot:
                add("Fundamental-Snapshot für Beta", 0, 1, "Zuerst Statement-Daten speichern")
            elif snapshot.get("beta") is None:
                stats = price_stats.get(ticker) or {}
                common_days = stats.get("common_days") or 0
                source = ((snapshot.get("metadata_json") or {}).get("data_sources") or {}).get("beta")
                newest_common = stats.get("newest_common")
                if common_days < 91:
                    why = "Zu wenige gemeinsame gültige Kurstage mit SPY"
                elif source == "unavailable":
                    why = "Lokale Kursreihe ergibt einen nicht belastbaren Extremwert; Yahoo liefert kein Beta"
                elif newest_common and (date.today() - newest_common).days > 14:
                    why = "Gemeinsame Kursreihe mit SPY älter als 14 Tage"
                else:
                    why = reason or "Lokale Berechnung wegen Kurslücken oder Ausreißern nicht belastbar; Yahoo liefert kein Beta"
                add("Beta", common_days, "91 gemeinsame Kurstage oder Yahoo-Beta", why)
        elif group == "assessment":
            days = (price_stats.get(ticker) or {}).get("price_days") or 0
            if days < 50:
                add("Kursdaten für Folgebewertung", days, 50, "Kursverlauf für eine Bewertung noch zu kurz")
            elif status in {"waiting_source", "error"}:
                add("Bewertbare Kursdaten", days, 50, reason or message or "Kursreihe nicht bewertbar")
        elif status in {"waiting_source", "error"}:
            add("Quelldaten", "", "", reason or message or "Prüfung offen")
    return rows


def missing_report_csv() -> str:
    with engine.connect() as connection:
        work_items = [dict(row) for row in connection.execute(text("""
            SELECT ticker, data_group, status, result_json, payload_json, error, checked_at, due_at
            FROM refresh_work_items
            WHERE ticker <> '*' AND status IN ('waiting_source', 'error', 'queued')
              AND data_group IN ('statements', 'beta', 'assessment')
            ORDER BY ticker, data_group
        """)).mappings()]
        tickers = sorted({item["ticker"] for item in work_items})
        snapshots = {}
        if tickers:
            snapshots = {row["ticker"]: dict(row) for row in connection.execute(text("""
                SELECT DISTINCT ON (ticker) ticker, metadata_json, fiscal_period, beta, as_of
                FROM fundamental_snapshots WHERE ticker = ANY(:tickers)
                ORDER BY ticker, as_of DESC, updated_at DESC
            """), {"tickers": tickers}).mappings()}
        price_tickers = sorted({item["ticker"] for item in work_items
                                if item["data_group"] in {"beta", "assessment"}})
        price_stats = {}
        if price_tickers:
            price_stats = {row["ticker"]: dict(row) for row in connection.execute(text("""
                SELECT i.ticker,
                       count(DISTINCT p.date) FILTER (WHERE p.close > 0) AS price_days,
                       count(DISTINCT p.date) FILTER
                           (WHERE p.adj_close > 0 AND spy.adj_close > 0) AS common_days,
                       max(p.date) FILTER
                           (WHERE p.adj_close > 0 AND spy.adj_close > 0) AS newest_common
                FROM instruments i
                LEFT JOIN price_bars p ON p.instrument_id = i.id AND p.date >= current_date - 400
                LEFT JOIN price_bars spy ON spy.date = p.date AND spy.instrument_id =
                    (SELECT id FROM instruments WHERE ticker = 'SPY' LIMIT 1)
                WHERE i.ticker = ANY(:tickers)
                GROUP BY i.ticker
            """), {"tickers": price_tickers}).mappings()}
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(HEADERS)
    writer.writerows(build_missing_rows(work_items, snapshots, price_stats))
    return output.getvalue()
