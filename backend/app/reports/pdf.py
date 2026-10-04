"""A4 vector report with embedded fonts, flowing tables and deterministic rendering."""
import base64
from datetime import date, datetime
from io import BytesIO
import math
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Image, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.reports.model import InvestmentReport

# ReportLab ships Bitstream Vera with its redistribution license, including in wheels.
_font_dir = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Report", str(_font_dir / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("ReportBold", str(_font_dir / "VeraBd.ttf")))
INK = colors.HexColor("#172033")
TEAL = colors.HexColor("#0f766e")
MUTED = colors.HexColor("#687386")
BORDER = colors.HexColor("#e3e8ef")
WIDTH = A4[0] - 88
BODY = ParagraphStyle("Body", fontName="Report", fontSize=9, leading=13, textColor=INK,
                      spaceAfter=5, splitLongWords=True)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8, leading=11, textColor=MUTED)
HEADING = ParagraphStyle("Heading", parent=BODY, fontName="ReportBold", fontSize=14,
                         leading=19, spaceBefore=17, spaceAfter=9)
TITLE = ParagraphStyle("Title", parent=HEADING, fontSize=25, leading=31)
KICKER = ParagraphStyle("Kicker", parent=SMALL, fontName="ReportBold", textColor=TEAL,
                        fontSize=7.5, leading=10, spaceAfter=3)
LABELS = {
    "fundamental": "Fundamental", "technical": "Technisch", "trend": "Trend", "risk": "Risiko",
    "overall": "Gesamtbewertung", "moving_averages": "Gleitende Durchschnitte", "chart_behavior": "Chartverhalten",
    "as_of": "Datenstand", "source": "Quelle", "prices": "Kurse", "fx_conversion": "Wechselkurs (Kurs- zu Positionswährung)", "data_status": "Datenstatus", "data_quality": "Datenqualität",
    "last_close": "Letzter Schlusskurs", "change_pct": "Kursänderung (%)", "atr_pct": "ATR (%)",
    "volume_ratio_50d": "Volumen / 50-Tage-Mittel", "dollar_volume_mio": "Handelsvolumen (Mio. USD)",
    "cmf_20": "Chaikin Money Flow (20)", "drawdown_52w_pct": "Abstand 52-Wochen-Hoch (%)",
    "rs_rating": "RS-Rating", "rs_percentile": "RS-Perzentil", "next_earnings_calendar_days": "Tage bis Earnings",
    "next_earnings_trading_days": "Handelstage bis Earnings", "buy_date": "Kaufdatum", "entry_price": "Kaufpreis",
    "current_price": "Aktueller Positionskurs", "current_price_source": "Kursquelle", "shares": "Stückzahl", "invested_amount": "Investierter Betrag",
    "market_value": "Aktueller Positionswert", "pnl_abs": "Gewinn / Verlust absolut", "pnl_pct": "Gewinn / Verlust (%)",
    "currency": "Währung", "stop_price": "Stop-Preis", "stop_pct": "Stop-Abstand zum Kauf (%)",
    "position_loss_risk": "Risiko vom Positionskurs bis Stop", "position_loss_risk_pct": "Risiko bis Stop (%)",
    "note": "Notiz", "notes": "Notizen", "name": "Name", "status": "Status", "message": "Hinweis",
    "buy": "Kauf", "sell": "Verkauf", "ex_post": "Ex-Post Analyse", "entry_type": "Eintragstyp",
    "trade_date": "Handelsdatum", "price": "Preis", "stop_distance_pct": "Stop-Abstand (%)",
    "realized_pnl_eur": "Realisiertes Ergebnis (EUR)", "realized_pnl_pct": "Realisiertes Ergebnis (%)",
    "basis_text": "Ursprüngliche Begründung / Setup", "primary_reasons": "Hauptgründe",
    "sell_reason": "Verkaufsgrund", "alternative_entry_text": "Alternativer Einstieg",
    "sell_assessment": "Automatische Verkaufsbewertung", "realized_pnl": "Realisiertes Ergebnis (Eintragswährung)",
    "fx_policy": "Historische Währungsumrechnung", "fx_carried_quotes": "Verwendete vorherige FX-Kurse",
    "quote_date": "Datum des FX-Kurses", "date": "Kurstag",
    "fees": "Gebühren", "tax": "Steuern", "allocations": "FIFO-Kaufzuordnung",
    "cost_basis": "Einstand inklusive Kaufkosten", "net_proceeds": "Nettoverkaufserlös", "pnl": "Ergebnis",
    "remaining_shares": "Verbleibende Stückzahl", "unallocated_shares": "Nicht zugeordnete Stückzahl",
    "allocation_method": "Zuordnungsmethode", "cutoff": "Historische Datengrenze", "method": "Bewertungsmethode",
    "evaluation": "Bewertung", "questionnaire": "Fragebogen", "portfolio_snapshot": "Position bei Erfassung",
    "market_snapshot": "Marktumfeld bei Erfassung", "created_at": "Erfasst am", "updated_at": "Zuletzt geändert",
    "checks": "Kriterien", "warnings": "Warnungen", "detail": "Erläuterung", "label": "Kriterium",
    "passed": "Kriterium erfüllt", "active": "Aktiv", "available": "Bewertbar", "score": "Score",
    "weight": "Gewichtung", "weight_pct": "Gewichtung (%)", "severity": "Schweregrad",
    "fundamentals": "Fundamentaldaten", "earnings": "Quartalszahlen", "drivers": "Treiber",
    "chart_signals": "Chartsignale", "chart_signal_states": "Chartzustände", "metrics": "Kennzahlen",
    "overall_v2": "Gesamtbewertung v2", "technical_v2": "Technical v2",
    "fundamental_v2": "Fundamental v2", "chart_v2": "Chart v2",
    "moving_average_v2": "Moving Average v2", "setup": "Setup / Kontext",
    "eligibility": "Handelbarkeit", "score_relevant": "Score-relevant",
    "display_relevant": "Anzeigerelevant", "effective_weight": "Effektives Gewicht",
    "base_weight": "Basisgewicht", "available_weight": "Verfügbares Gewicht",
    "quarterly_eps_growth_pct": "EPS-Wachstum Quartal (%)", "annual_eps_growth_pct": "EPS-Wachstum Jahr (%)",
    "quarterly_revenue_growth_pct": "Umsatzwachstum Quartal (%)", "annual_revenue_growth_pct": "Umsatzwachstum Jahr (%)",
    "roe_pct": "Eigenkapitalrendite (%)", "profit_margin_pct": "Gewinnmarge (%)", "trailing_eps": "EPS (TTM)",
    "eps_quarter_history": "Quartals-EPS", "annual_eps_history": "Jahres-EPS", "revenue_quarter_history": "Quartalsumsätze",
    "annual_revenue_history": "Jahresumsätze", "roe_history": "Eigenkapitalrendite Historie",
    "health": "Positionsgesundheit", "health_score": "Gesundheitsscore", "display_label": "Verkaufsbewertung",
    "explanation_short": "Begründung", "emergency_features": "Notverkauf-Kriterien",
    "offensive_features": "Offensive Verkaufskriterien", "defensive_features": "Defensive Verkaufskriterien",
    "killer_signals": "Notverkauf-Signale", "tranche_signals": "Tranchensignale", "warning_signals": "Warnsignale",
    "watch_signals": "Beobachtungssignale", "manual": "Manuelle Verkaufsbewertung", "tranche_log": "Spätere Anpassungen / Tranchen",
    "strategy": "Verkaufsstrategie", "reason": "Begründung", "value": "Wert", "evidence": "Beleg",
    "recommendation_percent": "Empfohlener Verkauf (%)", "sell_now_percent": "Jetzt verkaufen (%)",
    "target_total_sold_percent": "Zielverkaufsanteil (%)", "already_sold_percent": "Bereits verkauft (%)",
    "next_tranche_trigger_price": "Kurs für nächste Tranche", "full_exit_price": "Kurs für vollständigen Ausstieg",
    "ampel_phase": "Marktampel", "volatility_regime": "Volatilitätsregime", "breadth_mode": "Marktbreite",
    "k4_rs_leadership": "Relative Stärke: Führungsqualität (K4)", "k13_rs_dynamics": "Relative Stärke: Verbesserung und Beschleunigung (K13)",
    "high_position": "Nähe zu Allzeit- und 52-Wochen-Hoch", "up_down_volume": "Up/Down Volume",
    "cmf": "CMF / Akkumulation", "fundamental_core": "Gewinn, Umsatz und Profitabilität",
    "k9_eps_sales_alignment": "Gewinn- und Umsatzwachstum im Einklang (K9)", "price_action_core": "Kurs- und Volumenverhalten",
    "k35_down_week_quality": "Verkaufsdruck in Verlustwochen (K35)", "k38_hh_hl_good_close": "Höhere Wochenhochs und -tiefs mit starkem Schluss (K38)",
    "price_above_200_sma": "Kurs > 200 SMA", "price_above_50_sma": "Kurs > 50 SMA",
    "price_above_21_ema": "Kurs > 21 EMA", "price_above_10_sma": "Kurs > 10 SMA",
    "ma_order": "MA-Reihenfolge", "persistence": "Beständigkeit über den Durchschnitten", "slope": "Richtung der Durchschnitte",
}
# Transport/state-machine fields are not investor data. Never fetch remote chart URLs.
SKIP = {"assessment_version", "reason_code", "source_transaction_id", "trade_group_id", "position_id", "buy_transaction_id", "ticker", "id", "linked_entry_id", "key", "tone", "verdict_tone", "snapshot_schema",
        "next_recommendation_state", "book_references", "raw_payload", "chart_images", "stock_snapshot",
        "points", "rs_history", "history", "error", "raw"}


def label(key):
    return LABELS.get(key, key.replace("_", " ").capitalize())


def value(item):
    if item is None:
        return "Nicht vorhanden"
    if isinstance(item, bool):
        return "Ja" if item else "Nein"
    if isinstance(item, float):
        if not math.isfinite(item):
            return "Nicht vorhanden"
        return f"{item:,.4f}".rstrip("0").rstrip(".").replace(",", "~").replace(".", ",").replace("~", ".")
    if isinstance(item, (date, datetime)):
        return item.isoformat()
    return str(item)


def paragraph(text, style=BODY):
    # All user text is literal, never ReportLab XML or an external resource.
    clean = "".join(c for c in value(text) if c in "\n\t" or ord(c) >= 32)
    clean = clean.replace("–", "-").replace("—", "-").replace("‑", "-").replace("→", " -> ").replace("←", " <- ")
    return Paragraph(escape(clean).replace("\n", "<br/>"), style)


def table(headers, rows, widths):
    result = LongTable([[paragraph(cell) for cell in headers]] +
                       [[paragraph(cell) for cell in row] for row in rows],
                       colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=0, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f5f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), .4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def summary_table(items):
    """Quiet dashboard-style KPI strip; values are supplied data, never inferred here."""
    cells = []
    for item_label, item_value in items:
        cells.append(Paragraph(
            f'<font name="ReportBold" size="7" color="#687386">{escape(value(item_label).upper())}</font>'
            f'<br/><font name="ReportBold" size="13" color="#172033">{escape(value(item_value))}</font>',
            BODY,
        ))
    result = LongTable([cells], colWidths=[WIDTH / len(cells)] * len(cells), hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), .5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), .5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return result


def fields(data, prefix=""):
    """Flatten complete nested criteria without losing false/zero or long explanations."""
    if isinstance(data, dict):
        for key, item in data.items():
            if key in SKIP or key.startswith("_") or item == "" or item == [] or item == {}:
                continue
            path = f"{prefix} / {label(key)}" if prefix else label(key)
            yield from fields(item, path)
    elif isinstance(data, list):
        for index, item in enumerate(data, 1):
            yield from fields(item, f"{prefix} {index}")
    else:
        yield prefix, value(data)


def add_data(story, title, data):
    if not data:
        return
    story.extend([CondPageBreak(90), paragraph(title, HEADING)])
    # Compact criteria arrays retain all available evidence and scoring fields.
    if isinstance(data, list) and all(isinstance(item, dict) and "label" in item for item in data):
        rows = []
        for item in data:
            evidence = "\n".join(f"{key}: {val}" for key, val in fields(
                {k: v for k, v in item.items() if k != "label"}))
            rows.append([item["label"], evidence])
        story.append(table(["Kriterium", "Wert / Bewertung / Erläuterung"], rows, [160, WIDTH - 160]))
        return
    if isinstance(data, dict):
        scalars = {k: v for k, v in data.items() if not isinstance(v, (dict, list))}
        nested = [(k, v) for k, v in data.items() if isinstance(v, (dict, list)) and k not in SKIP and v]
    else:
        scalars, nested = data, []
    batch = []
    for key, text in fields(scalars):
        if len(text) > 450:
            if batch:
                story.append(table(["Merkmal", "Wert / Erläuterung"], batch, [185, WIDTH - 185]))
                batch = []
            story.extend([paragraph(key, HEADING), paragraph(text)])
        else:
            batch.append((key, text))
    if batch:
        story.append(table(["Merkmal", "Wert / Erläuterung"], batch, [185, WIDTH - 185]))
    for key, item in nested:
        add_data(story, label(key), item)


def status_text(status):
    return {
        "available": "Bewertbar", "partial": "Teilweise", "neutral": "Neutral",
        "limited": "Eingeschränkt", "insufficient_history": "Zu wenig Historie",
        "missing": "Nicht vorhanden",
    }.get(status, label(status) if status else "Nicht vorhanden")


def add_v2_assessment(story, assessment):
    groups = (
        ("Technische Bewertung", assessment.get("technical_v2")),
        ("Fundamentale Bewertung", assessment.get("fundamental_v2")),
        ("Chartbewertung", assessment.get("chart_v2")),
        ("Gleitende Durchschnitte", assessment.get("moving_average_v2")),
    )
    available = [(title, detail) for title, detail in groups if isinstance(detail, dict) and detail]
    if not available:
        return
    story.extend([CondPageBreak(90), paragraph("Bewertung im Detail", HEADING)])
    story.append(paragraph("Basis ist der konfigurierte Anteil innerhalb der Bewertung. Effektiv ist der verwendete Anteil nach Umverteilung fehlender Bestandteile. Die Gesamtbewertung und die folgenden Gruppen verwenden dieselben gespeicherten Scores.", SMALL))
    overall = assessment.get("overall_v2") or {}
    if overall.get("status") == "limited":
        available_weight = overall.get("available_weight")
        suffix = f" ({value(available_weight * 100)} % Gewichtung verfügbar)" if isinstance(available_weight, (int, float)) else ""
        story.append(paragraph(f"Gesamtbewertung eingeschränkt{suffix}.", SMALL))
    for title, detail in available:
        score = detail.get("score")
        score_text = f"{concise_number(score)} / 100" if isinstance(score, (int, float)) else status_text(detail.get("status"))
        rows = []
        for key, component in (detail.get("components") or {}).items():
            if not isinstance(component, dict):
                continue
            component_score = component.get("score")
            base = component.get("base_weight")
            effective = component.get("effective_weight")
            weight_bits = []
            if isinstance(base, (int, float)):
                weight_bits.append(f"Basis {concise_number(base * 100)} %")
            if isinstance(effective, (int, float)):
                weight_bits.append(f"effektiv {concise_number(effective * 100)} %")
            rows.append([
                label(key),
                f"{concise_number(component_score)} / 100" if isinstance(component_score, (int, float)) else "–",
                status_text(component.get("status")),
                " · ".join(weight_bits) or "–",
            ])
        if rows:
            score_table = compact_table(["Kriterium", "Score", "Status", "Gewichtung"], rows, [180, 88, 75, WIDTH - 343])
            story.extend([CondPageBreak(min(700, score_table.wrap(WIDTH, 730)[1] + 60)), paragraph(f"{title}  ·  {score_text}", HEADING), score_table])


def add_assessment(story, assessment, title="Aktienbewertung"):
    story.extend([CondPageBreak(190), paragraph(title, HEADING)])
    if not assessment or assessment.get("source") == "missing":
        story.append(paragraph("Keine Bewertung gespeichert."))
        return
    story.append(paragraph(assessment.get("verdict_label", "")))
    story.append(paragraph(assessment.get("verdict_text", "")))
    for text in (assessment.get("message"),):
        if text:
            story.append(paragraph(text, SMALL))
    scores = dict(assessment.get("scores", {}))
    for key, detail_key in {"overall": "overall_v2", "technical": "technical_v2", "fundamental": "fundamental_v2", "moving_averages": "moving_average_v2", "chart_behavior": "chart_v2"}.items():
        if isinstance(assessment.get(detail_key), dict) and assessment[detail_key]:
            scores[key] = assessment[detail_key].get("score")
    if scores:
        chart = Drawing(WIDTH, len(scores) * 25 + 8)
        for index, (key, score) in enumerate(scores.items()):
            if not isinstance(score, (float, int)) or not math.isfinite(score):
                continue
            y = len(scores) * 25 - index * 25
            chart.add(String(0, y, label(key), fontName="Report", fontSize=9, fillColor=INK))
            chart.add(Rect(180, y - 2, 235, 9, fillColor=BORDER, strokeColor=None))
            chart.add(Rect(180, y - 2, 235 * max(0, min(100, score)) / 100, 9, fillColor=TEAL, strokeColor=None))
            chart.add(String(430, y, f"{concise_number(score)} / 100", fontName="Report", fontSize=9, fillColor=INK))
        story.append(chart)
    add_messages(story, "Wichtigste Treiber", assessment.get("drivers"))
    add_messages(story, "Warnungen und Recherchebedarf", assessment.get("warnings"))
    add_v2_assessment(story, assessment)
    add_setup(story, assessment.get("setup"))
    add_chart_states(story, assessment)
    add_chart_signals(story, assessment)
    earnings = assessment.get("earnings") or {}
    if earnings:
        section_heading(story, "Nächster Berichtstermin")
        story.append(paragraph(earnings.get("message") or f"Nächste Quartalszahlen: {earnings.get('next_earnings_date') or 'nicht gespeichert'}"))
    checks = assessment.get("checks") or []
    if checks:
        section_heading(story, "Kriterien im Überblick")
        rows = []
        for check in checks:
            if check.get("label") == "Fundamental-Datenquelle":
                continue
            detail = str(check.get("detail") or "")
            result = "Nicht bewertbar" if detail.startswith("Nicht verfügbar") else "Nicht anwendbar" if "nicht anwendbar" in detail.lower() else "Erfüllt" if check.get("passed") is True else "Nicht erfüllt" if check.get("passed") is False else "Nicht bewertbar"
            rows.append([check.get("label", ""), result, detail])
        if rows:
            story.append(compact_table(["Kriterium", "Ergebnis", "Beobachtung"], rows, [185, 90, WIDTH - 275]))
    add_data_quality(story, assessment.get("data_quality"))


def add_chart(story, prices):
    points = [p for p in prices.get("points", []) if isinstance(p.get("close"), (int, float)) and math.isfinite(p["close"])]
    if len(points) < 2:
        return
    story.extend([CondPageBreak(210), paragraph("Kursverlauf · Schlusskurse", HEADING)])
    story.append(paragraph(f"{points[0]['date']} bis {points[-1]['date']} · {prices.get('currency') or 'Währung nicht gespeichert'}", SMALL))
    chart = Drawing(WIDTH, 165)
    low, high = min(p["close"] for p in points), max(p["close"] for p in points)
    span = high - low or max(abs(high) * .01, 1)
    coords = []
    for i, p in enumerate(points):
        coords.extend([48 + i / (len(points) - 1) * (WIDTH - 60), 25 + (p["close"] - low) / span * 120])
    for i in range(3):
        y = 25 + i * 60
        chart.add(Line(48, y, WIDTH - 12, y, strokeColor=BORDER, strokeWidth=.5))
        chart.add(String(0, y - 3, f"{low + span * i / 2:.2f}", fontName="Report", fontSize=8, fillColor=MUTED))
    chart.add(PolyLine(coords, strokeColor=TEAL, strokeWidth=1.5))
    story.append(chart)


def add_images(story, images):
    for key, data in images.items():
        if not data:
            continue
        title = {"daily_chart": "Tageschart", "weekly_chart": "Wochenchart"}.get(key, label(key))
        try:
            if not data.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")) or len(data) > 16_000_000:
                raise ValueError("Unsupported chart")
            raw = BytesIO(base64.b64decode(data.split(",", 1)[1], validate=True))
            from PIL import Image as PILImage
            with PILImage.open(raw) as source:
                if source.width * source.height > 25_000_000:
                    raise ValueError("Chart too large")
                source.load()
                converted = BytesIO()
                source.convert("RGB").save(converted, format="PNG")
            converted.seek(0)
            picture = Image(converted)
            scale = min(WIDTH / picture.imageWidth, 340 / picture.imageHeight)
            picture.drawWidth = picture.imageWidth * scale
            picture.drawHeight = picture.imageHeight * scale
            story.extend([CondPageBreak(200), paragraph(title, HEADING), picture])
        except Exception:
            story.append(paragraph(f"{title}: gespeichertes Bild nicht darstellbar.", SMALL))


# Investor-facing renderers deliberately select display fields. Full diagnostic
# payloads remain available through the explicit technical appendix.
def concise_number(item, suffix=""):
    if isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
        return f"{item:,.1f}".replace(",", "~").replace(".", ",").replace("~", ".") + suffix
    return "Nicht verfügbar"


def compact_table(headers, rows, widths, tones=None):
    result = LongTable([[paragraph(cell, SMALL) for cell in headers]] +
                       [[paragraph(cell, SMALL) for cell in row] for row in rows],
                       colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
    rules = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f5f2")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LINEBELOW", (0, 0), (-1, -1), .4, BORDER),
             ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for index, tone in enumerate(tones or [], 1):
        if tone in {"warning", "missing"}:
            rules.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#fff7ed" if tone == "warning" else "#f8fafc")))
    result.setStyle(TableStyle(rules))
    return result


def section_heading(story, title):
    story.extend([CondPageBreak(100), paragraph(title, HEADING)])


def add_messages(story, title, messages):
    if messages:
        section_heading(story, title)
        for message in dict.fromkeys(str(item) for item in messages if item):
            story.append(paragraph(message))


SIGNAL_NAMES = {
    "Negative Kurslücken bei hohem Vol.": "Negative Kurslücken bei hohem Volumen",
    "Preisrückgänge bei hohem Vol.": "Kursrückgänge bei hohem Volumen",
    "Mehr Verlust- als Gewinntage mit hohem Vol.": "Volumen an Verlust- und Gewinntagen",
    "RS-Linie unter 21-EMA": "Relative Stärke vs. 21-Tage-Linie",
    "RS-Linie unter 50-SMA": "Relative Stärke vs. 50-Tage-Linie",
    "RS-Linie fällt": "Entwicklung der relativen Stärke",
    "RS-Linie deutlich unter Hoch": "Relative Stärke vs. 52-Wochen-Hoch",
    "Leben unter den Durchschnitten": "Kurs unter wichtigen Durchschnittslinien",
    "Großer Abstand zu Durchschnitten": "Abstand zu den Durchschnittslinien",
}


def signal_explanation(name, detail):
    import re
    match = re.fullmatch(r"(\d+)/(\d+) Tage · Warnung ab (\d+)", detail)
    if match:
        count, days, threshold = map(int, match.groups())
        event = "bearisher Outside Day" if name == "Bearisher Outside Day" else "Bearish-Engulfing-Muster" if name == "Bearish Engulfing" else "Stau-Tag" if name == "Stau-Tage" else "Ereignis"
        text = f"Kein {event} in den letzten {days} Handelstagen." if count == 0 else f"{count} {'Ereignis' if count == 1 else 'Ereignisse'} in den letzten {days} Handelstagen."
        detail = f"{text} Warnsignal ab {threshold} {'Auftreten' if threshold == 1 else 'Ereignissen'}."
    detail = re.sub(r"(\d+)T\b", r"\1 Handelstage", detail)
    detail = detail.replace("5W-Trend", "Trend über 5 Wochen")
    if name == "Stau-Tage":
        detail += " Stau-Tage sind Tage mit wenig Kursfortschritt trotz erhöhtem Handelsvolumen; sie können auf Verkaufsdruck hinweisen."
    return detail


def add_chart_states(story, assessment):
    states = assessment.get("chart_signal_states") or {}
    if not states:
        return
    # Explicit flags are authoritative: unavailable is never interpreted as calm.
    rows, tones = [], []
    ordered = sorted(states.items(), key=lambda pair: 0 if pair[1].get("available") is True and pair[1].get("active") is True else 1 if pair[1].get("available") is not True else 2)
    active = sum(state.get("available") is True and state.get("active") is True for state in states.values())
    missing = sum(state.get("available") is not True or not isinstance(state.get("active"), bool) for state in states.values())
    for name, state in ordered:
        unavailable = state.get("available") is not True or not isinstance(state.get("active"), bool)
        status = "Daten fehlen" if unavailable else "Warnsignal aktiv" if state["active"] else "Unauffällig"
        rows.append([SIGNAL_NAMES.get(name, name), status, signal_explanation(name, str(state.get("detail") or "Keine Erläuterung gespeichert."))])
        tones.append("missing" if unavailable else "warning" if state["active"] else "good")
    state_table = compact_table(["Kriterium", "Einordnung", "Beobachtung / Warnschwelle"], rows, [135, 90, WIDTH - 225], tones)
    story.append(CondPageBreak(min(720, state_table.wrap(WIDTH, 730)[1] + 90)))
    section_heading(story, "Chartzustand: Warnsignale und unauffällige Kriterien")
    story.append(paragraph(f"{active} aktive Warnsignale. " + (f"{missing} Kriterien nicht bewertbar." if missing else "Alle aufgeführten Kriterien sind bewertbar."), SMALL))
    story.append(state_table)


def add_chart_signals(story, assessment):
    signals = assessment.get("chart_signals") or []
    if not signals:
        return
    section_heading(story, "Chartverhalten: aktuelle Signale")
    for category, title in [("positive", "Positiv"), ("negative", "Negativ"), ("neutral", "Neutral")]:
        selected = [signal for signal in signals if signal.get("category") == category]
        if not selected:
            continue
        story.append(paragraph(title, KICKER))
        story.append(compact_table(["Signal", "Beobachtung"], [
            [SIGNAL_NAMES.get(item.get("label"), item.get("label", "")), item.get("detail") or "Aktuelles Chartsignal"]
            for item in selected], [190, WIDTH - 190], ["warning" if category == "negative" else "good"] * len(selected)))


def add_setup(story, setup):
    if not setup:
        return
    story.append(CondPageBreak(240))
    section_heading(story, "Trend und Abstand zu den Durchschnittslinien")
    distances = setup.get("moving_average_distances") or {}
    valid = [item for item in distances.values() if isinstance(item, dict) and isinstance(item.get("distance_pct"), (int, float)) and isinstance(item.get("threshold_pct"), (int, float))]
    if distances and len(valid) == len(distances):
        within = all(abs(item["distance_pct"]) <= item["threshold_pct"] for item in valid)
        story.append(paragraph("Alle Abstände liegen innerhalb der zulässigen Grenzen." if within else "Mindestens ein Abstand überschreitet die zulässige Grenze."))
    elif distances:
        story.append(paragraph("Einige Durchschnittsabstände sind wegen fehlender Daten nicht bewertbar."))
    rows = []
    for name, item in distances.items():
        distance, threshold = item.get("distance_pct"), item.get("threshold_pct")
        known = isinstance(distance, (int, float)) and isinstance(threshold, (int, float))
        rows.append([name, concise_number(distance, " %"), f"±{concise_number(threshold, ' %')}", "Innerhalb der Grenze" if known and abs(distance) <= threshold else "Grenze überschritten" if known else "Daten fehlen"])
    if rows:
        story.append(compact_table(["Durchschnitt", "Abstand", "Grenze", "Einordnung"], rows, [110, 90, 80, WIDTH - 280]))
    descriptions = {"test_21_ema": "Test der 21-Tage-Linie", "test_50_sma": "Test der 50-Tage-Linie", "natural_reaction": "Normaler Rücksetzer"}
    contexts = [f"{name}: {'erkannt' if setup[key] else 'nicht erkannt'}" for key, name in descriptions.items() if isinstance(setup.get(key), bool)]
    if contexts:
        story.append(paragraph(" · ".join(contexts), SMALL))


def add_data_quality(story, quality):
    if not quality:
        return
    story.append(CondPageBreak(220))
    section_heading(story, "Datenbasis und Aktualität")
    rows = []
    for key, item in quality.items():
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        status_label = {"fresh": "Aktuell", "stale": "Veraltet", "missing": "Daten fehlen", "not_applicable": "Nicht anwendbar"}.get(status, status_text(status))
        rows.append([item.get("label") or label(key), status_label, item.get("as_of") or "Kein Datenstand gespeichert"])
    if rows:
        story.append(compact_table(["Datenbereich", "Einordnung", "Datenstand"], rows, [185, 110, WIDTH - 295]))
    story.append(paragraph("Datenstände beziehen sich auf den jeweiligen Berichts- oder Handelstag. Quartalsdaten und 13F-Meldungen folgen anderen Aktualisierungszyklen als Kurse.", SMALL))


def add_selected_values(story, title, data, keys):
    rows = [[display, concise_number(data[key], suffix) if suffix is not None else value(data[key])] for key, display, suffix in keys if data.get(key) is not None]
    if rows:
        section_heading(story, title)
        story.append(compact_table(["Kennzahl", "Wert"], rows, [260, WIDTH - 260]))


def add_fundamentals(story, data, title="Fundamentale Entwicklung"):
    section_heading(story, title)
    source = " · ".join(str(data[key]) for key in ("source", "fiscal_period", "as_of") if data.get(key))
    if source:
        story.append(paragraph(f"Quelle / Berichtsstand: {source}", SMALL))
    add_selected_values(story, "Wachstum und Profitabilität", data, [
        ("quarterly_eps_growth_pct", "EPS-Wachstum gegenüber Vorjahresquartal", " %"),
        ("annual_eps_growth_pct", "Jährliches EPS-Wachstum", " %"),
        ("quarterly_revenue_growth_pct", "Umsatzwachstum gegenüber Vorjahresquartal", " %"),
        ("annual_revenue_growth_pct", "Jährliches Umsatzwachstum", " %"),
        ("roe_pct", "Eigenkapitalrendite", " %"), ("profit_margin_pct", "Gewinnmarge", " %"),
        ("trailing_eps", "Gewinn je Aktie der letzten vier Quartale", ""),
    ])
    definitions = [
        ("eps_quarter_history", "Gewinn je Aktie: Quartale", "eps_current_quarter", "eps_same_quarter_last_year", "eps_growth_yoy_pct"),
        ("revenue_quarter_history", "Umsatz: Quartale", "revenue_current_quarter", "revenue_same_quarter_last_year", "revenue_growth_yoy_pct"),
        ("annual_eps_history", "Gewinn je Aktie: Jahre", "eps_current_year", "eps_previous_year", "eps_growth_yoy_pct"),
        ("annual_revenue_history", "Umsatz: Jahre", "revenue_current_year", "revenue_previous_year", "revenue_growth_yoy_pct"),
    ]
    for key, heading, current, previous, growth in definitions:
        history = data.get(key) or []
        if not history:
            continue
        rows = []
        for item in history[:8]:
            period = item.get("fiscal_period") or item.get("fiscal_year") or item.get("report_date") or item.get("period_end_date") or "Nicht gespeichert"
            rows.append([period, concise_number(item.get(current)), concise_number(item.get(previous)), concise_number(item.get(growth), " %")])
        story.extend([CondPageBreak(min(550, 70 + len(rows) * 30)), paragraph(heading, KICKER), compact_table(["Berichtsperiode", "Aktuell", "Vorjahr", "Wachstum"], rows, [135, 125, 125, WIDTH - 385])])
        if len(history) > 8:
            story.append(paragraph(f"Die jüngsten 8 von {len(history)} gespeicherten Perioden. Vollständige Historie im optionalen technischen Anhang.", SMALL))
    roe = data.get("roe_history") or []
    if roe:
        story.extend([CondPageBreak(100), paragraph("Eigenkapitalrendite: Jahre", KICKER), compact_table(["Jahr", "Eigenkapitalrendite"], [[item.get("fiscal_year") or item.get("fiscal_period") or "Nicht gespeichert", concise_number(item.get("roe_pct"), " %")] for item in roe[:8]], [180, WIDTH - 180])])
    if not any(data.get(key) is not None for key in ("quarterly_eps_growth_pct", "annual_eps_growth_pct", "trailing_eps", "annual_revenue_growth_pct")):
        story.append(paragraph("Keine belastbaren Wachstumskennzahlen gespeichert.", SMALL))


def add_relative_strength(story, data):
    item = data.get("item") if isinstance(data.get("item"), dict) else data
    story.append(CondPageBreak(240))
    section_heading(story, "Relative Stärke im Aktienvergleich")
    if data.get("found") is False or not item or (data.get("item") is None and "item" in data):
        story.append(paragraph("Keine Relative-Stärke-Daten gespeichert."))
        return
    rating = item.get("rating", item.get("rs_rating"))
    story.append(paragraph(f"RS-Rating: {concise_number(rating)} von 99 · Datenstand {item.get('date') or data.get('as_of') or 'nicht gespeichert'}"))
    story.append(paragraph("Das RS-Rating vergleicht die Kursentwicklung mit anderen Aktien. Die RS-Linie vergleicht die Aktie mit ihrem Referenzindex; beide Kennzahlen sind verschieden.", SMALL))
    rows = [[period, concise_number(item.get(ret), " %"), concise_number(item.get(excess), " Prozentpunkte")] for period, ret, excess in [("3 Monate", "ret_3m", "excess_return_3m"), ("6 Monate", "ret_6m", "excess_return_6m"), ("12 Monate", "ret_12m", "excess_return_12m")]]
    story.append(compact_table(["Zeitraum", "Kursentwicklung", "Mehr-/Minderrendite zum Index"], rows, [110, 150, WIDTH - 260]))
    if isinstance(item.get("new_high_52w"), bool):
        story.append(paragraph("Die RS-Linie erreicht ein neues 52-Wochen-Hoch." if item["new_high_52w"] else "Die RS-Linie liegt unter ihrem 52-Wochen-Hoch.", SMALL))


def add_institutional(story, data):
    item = data.get("item") if isinstance(data.get("item"), dict) else data
    section_heading(story, "Institutionelle Anleger / 13F")
    if not item or ("item" in data and data["item"] is None):
        story.append(paragraph("Keine institutionellen Meldedaten gespeichert."))
        return
    trend = {"positive": "Zunehmende Unterstützung", "negative": "Rückläufige Unterstützung", "neutral": "Uneinheitlich / neutral", "missing": "Nicht bewertbar"}.get(item.get("trend"), "Nicht eingeordnet")
    story.append(paragraph(f"{trend} · Berichtsquartal {item.get('report_period') or data.get('as_of') or 'nicht gespeichert'}"))
    rows = [[name, concise_number(item.get(current)), concise_number(item.get(previous)), concise_number(item.get(delta), suffix)] for name, current, previous, delta, suffix in [
        ("Meldende institutionelle Halter", "holder_count", "previous_holder_count", "holder_count_delta", ""),
        ("Große institutionelle Halter", "large_holder_count", "previous_large_holder_count", "large_holder_delta", ""),
        ("Gemeldete Aktien", "total_shares", "previous_total_shares", "total_shares_delta_pct", " %"),
        ("Gemeldeter Positionswert (USD)", "total_value_usd", "previous_total_value_usd", "total_value_delta_pct", " %"),
    ]]
    story.append(compact_table(["Kennzahl", "Aktuell", "Vorquartal", "Änderung"], rows, [170, 115, 115, WIDTH - 400]))
    story.append(paragraph("13F-Meldungen sind Quartalsaufnahmen mit Veröffentlichungsverzug. Sie bilden nicht die aktuellen Käufe oder Verkäufe institutioneller Anleger ab.", SMALL))


def add_market(story, data, title="Marktumfeld"):
    section_heading(story, title)
    if not data:
        story.append(paragraph("Kein Marktumfeld gespeichert."))
        return
    trend = data.get("trend_ampel") or {}
    phase = trend.get("phase_label") or data.get("ampel_phase") or "Nicht gespeichert"
    story.append(paragraph(f"Marktampel: {phase} · Datenstand {data.get('as_of') or trend.get('as_of') or 'nicht gespeichert'}"))
    for text in (trend.get("phase_reason"), data.get("action")):
        if text:
            story.append(paragraph(text))
    powertrend = trend.get("powertrend_state")
    if powertrend:
        story.append(paragraph("Powertrend: " + {"on": "aktiv", "off": "nicht aktiv", "under_pressure": "unter Druck"}.get(powertrend, "nicht eingeordnet") + ". Dieser Zustand wird unabhängig von der Marktampel bewertet.", SMALL))
    kpis = data.get("kpis") or []
    rows = [[item.get("label", ""), item.get("value", ""), item.get("detail", "")] for item in kpis if item.get("label") != "Coverage"]
    if rows:
        story.append(compact_table(["Marktindikator", "Wert", "Einordnung"], rows, [155, 85, WIDTH - 240]))
    else:
        add_selected_values(story, "Marktindikatoren", data, [("breadth_mode", "Marktbreite", None), ("volatility_regime", "Volatilitätsregime", None), ("pct_above_50sma", "Aktien über 50-Tage-Linie", " %"), ("pct_above_200sma", "Aktien über 200-Tage-Linie", " %")])
    breadth = data.get("equal_weight_breadth") or {}
    if breadth.get("message"):
        story.append(paragraph(breadth["message"], SMALL))
    coverage = data.get("coverage_ratio")
    if isinstance(coverage, (int, float)):
        story.append(paragraph(f"Marktdaten-Abdeckung: {concise_number(coverage * 100, ' %')}." + (" Marktindikatoren sind nur eingeschränkt belastbar." if coverage < .95 else ""), SMALL))


def add_investor_section(story, title, data):
    if title.startswith("Marktumfeld"):
        add_market(story, data, title)
    elif title == "Fundamentaldaten":
        add_fundamentals(story, data)
    elif title == "Relative Stärke":
        add_relative_strength(story, data)
    elif title == "Institutionelle Anleger / 13F":
        add_institutional(story, data)
    else:
        add_data(story, title, data)


def add_technical_appendix(story, report):
    from dataclasses import asdict
    import json
    import textwrap
    story.extend([PageBreak(), paragraph("Technischer Anhang", TITLE), paragraph("Vollständige gespeicherte Reportdaten, Regeln, Schwellenwerte und Diagnosefelder. Eingebettete Chartbilder sind im Report dargestellt; ihre Bildkodierung wird hier ausgelassen.", SMALL)])
    def without_images(data):
        if isinstance(data, dict):
            return {key: without_images(item) for key, item in data.items() if key != "chart_images"}
        if isinstance(data, list):
            return [without_images(item) for item in data]
        return data
    def json_lines(data):
        if isinstance(data, dict) and any(isinstance(item, (dict, list)) for item in data.values()):
            lines = ["{"]
            entries = list(data.items())
            for index, (key, item) in enumerate(entries):
                child = json_lines(item)
                lines.append("  " + json.dumps(key, ensure_ascii=False) + ": " + child[0])
                lines.extend("  " + line for line in child[1:])
                if index < len(entries) - 1:
                    lines[-1] += ","
            return [*lines, "}"]
        if isinstance(data, list):
            lines = ["["]
            for index, item in enumerate(data):
                lines.extend("  " + line for line in json_lines(item))
                if index < len(data) - 1:
                    lines[-1] += ","
            return [*lines, "]"]
        return [json.dumps(data, ensure_ascii=False, default=str)]
    payload = "\n".join(json_lines(without_images(asdict(report))))
    appendix_style = ParagraphStyle("Appendix", parent=SMALL, fontSize=6.5, leading=9, spaceAfter=0)
    # Short literal paragraphs keep every raw field and value while allowing
    # page breaks even in very long notes or histories.
    for line in payload.splitlines():
        for fragment in textwrap.wrap(line, width=105, replace_whitespace=False, drop_whitespace=False) or [""]:
            story.append(paragraph(fragment, appendix_style))


def render_report(report: InvestmentReport, *, include_technical_appendix: bool = False) -> bytes:
    output = BytesIO()
    timestamp = report.exported_at.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y %H:%M %Z")
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=44, rightMargin=44,
                            topMargin=61, bottomMargin=51, title=f"{report.ticker} Investment-Report",
                            author="Börse Dashboard", invariant=1, pageCompression=1)

    def frame(canvas, document):
        canvas.saveState()
        canvas.setFont("ReportBold", 8)
        canvas.setFillColor(TEAL)
        canvas.drawString(44, A4[1] - 32, "BÖRSE DASHBOARD  /  INVESTMENT REPORT")
        canvas.setFont("Report", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 44, A4[1] - 32, report.ticker)
        canvas.setStrokeColor(BORDER)
        canvas.line(44, 39, A4[0] - 44, 39)
        canvas.drawString(44, 26, f"Export {timestamp}")
        canvas.drawRightString(A4[0] - 44, 26, f"Seite {document.page}")
        canvas.restoreState()

    assessment = report.assessment
    close = report.prices.get("last_close")
    if close is None:
        close = assessment.get("metrics", {}).get("last_close")
    overall = None if assessment.get("source") == "missing" else (assessment.get("overall_v2") or {}).get("score")
    if overall is None and assessment.get("source") != "missing":
        overall = assessment.get("scores", {}).get("overall")
    verdict = assessment.get("verdict_label") or "Nicht bewertet"
    data_as_of = report.prices.get("last_date") or assessment.get("as_of") or "Unbekannt"
    currency = report.prices.get("currency") or report.currency
    story = [paragraph("INVESTMENT- UND TRADING-REPORT", KICKER), paragraph(report.name, TITLE), paragraph(
        " · ".join(filter(None, [report.ticker, report.isin, "Trade-Report" if report.trade_id else "Aktien-Report"])), SMALL)]
    story.extend([Spacer(1, 7), summary_table([
        ("Kurs", f"{value(close)} {currency}".strip()),
        ("Gesamtscore", f"{concise_number(overall)} / 100" if overall is not None else "–"),
        ("Urteil", verdict),
        ("Datenstand", data_as_of),
    ])])
    for notice in report.notices:
        story.append(paragraph(notice, SMALL))
    position_sections = [section for section in report.sections if section.title.startswith("Position")]
    other_sections = [section for section in report.sections if section not in position_sections]
    for section in position_sections:
        add_data(story, section.title, section.data)
    add_chart(story, report.prices)
    add_assessment(story, assessment)
    for section in other_sections:
        add_investor_section(story, section.title, section.data)
    if report.journal:
        story.append(paragraph("Handelstagebuch", HEADING))
    for entry in report.journal:
        title = f"{label(entry.get('entry_type', ''))} · {entry.get('trade_date', '')}"
        add_data(story, title, {k: v for k, v in entry.items() if k not in {"market_snapshot", "portfolio_snapshot"} and v is not None and v != ""})
        if entry.get("id") != report.trade_id:
            add_data(story, "Position bei Erfassung", entry.get("portfolio_snapshot", {}))
            add_data(story, "Marktumfeld bei Erfassung", entry.get("market_snapshot", {}))
        snapshot = entry.get("stock_snapshot", {})
        # Main historical assessment is already printed for the selected trade.
        if entry.get("id") != report.trade_id:
            add_assessment(story, snapshot.get("assessment", snapshot), f"Bewertung bei {title}")
        for key in ("fundamentals", "institutional_13f", "relative_strength"):
            if snapshot.get(key) and entry.get("id") != report.trade_id:
                add_investor_section(story, {"fundamentals": "Fundamentaldaten", "relative_strength": "Relative Stärke", "institutional_13f": "Institutionelle Anleger / 13F"}[key], snapshot[key])
        add_images(story, entry.get("chart_images", {}))
    story.append(Spacer(1, 12))
    story.append(paragraph("Datenbasis: gespeicherte Dashboard-Daten und bestehende Bewertungsregeln. "
                           "Fehlende Werte werden nicht geschätzt. Kurswährung und Positionswährung können abweichen. "
                           "Der Export verändert keine Positionen oder Verkaufssignale.", SMALL))
    if include_technical_appendix:
        add_technical_appendix(story, report)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return output.getvalue()
