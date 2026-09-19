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
from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

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
                         leading=19, spaceBefore=17, spaceAfter=9, keepWithNext=True)
TITLE = ParagraphStyle("Title", parent=HEADING, fontSize=25, leading=31)
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
    "questionnaire": "Fragebogen", "portfolio_snapshot": "Position bei Erfassung",
    "market_snapshot": "Marktumfeld bei Erfassung", "created_at": "Erfasst am", "updated_at": "Zuletzt geändert",
    "checks": "Kriterien", "warnings": "Warnungen", "detail": "Erläuterung", "label": "Kriterium",
    "passed": "Kriterium erfüllt", "active": "Aktiv", "available": "Verfügbar", "score": "Score",
    "weight": "Gewichtung", "weight_pct": "Gewichtung (%)", "severity": "Schweregrad",
    "fundamentals": "Fundamentaldaten", "earnings": "Quartalszahlen", "drivers": "Treiber",
    "chart_signals": "Chartsignale", "chart_signal_states": "Chartzustände", "metrics": "Kennzahlen",
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
}
# Transport/state-machine fields are not investor data. Never fetch remote chart URLs.
SKIP = {"ticker", "id", "linked_entry_id", "key", "tone", "verdict_tone", "snapshot_schema",
        "next_recommendation_state", "book_references", "raw_payload", "chart_images", "stock_snapshot",
        "points", "rs_history", "history", "error"}


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
    return Paragraph(escape(clean).replace("\n", "<br/>"), style)


def table(headers, rows, widths):
    result = LongTable([[paragraph(cell) for cell in headers]] +
                       [[paragraph(cell) for cell in row] for row in rows],
                       colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f5f2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), .4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
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
    story.append(paragraph(title, HEADING))
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


def add_assessment(story, assessment, title="Aktienbewertung"):
    story.append(paragraph(title, HEADING))
    if not assessment or assessment.get("source") == "missing":
        story.append(paragraph("Keine Bewertung gespeichert."))
        return
    story.append(paragraph(assessment.get("verdict_label", "")))
    story.append(paragraph(assessment.get("verdict_text", "")))
    for text in (assessment.get("message"),):
        if text:
            story.append(paragraph(text, SMALL))
    scores = assessment.get("scores", {})
    if scores:
        chart = Drawing(WIDTH, len(scores) * 25 + 8)
        for index, (key, score) in enumerate(scores.items()):
            if not isinstance(score, (float, int)) or not math.isfinite(score):
                continue
            y = len(scores) * 25 - index * 25
            chart.add(String(0, y, label(key), fontName="Report", fontSize=9, fillColor=INK))
            chart.add(Rect(180, y - 2, 235, 9, fillColor=BORDER, strokeColor=None))
            chart.add(Rect(180, y - 2, 235 * max(0, min(100, score)) / 100, 9, fillColor=TEAL, strokeColor=None))
            chart.add(String(430, y, f"{value(score)} / 100", fontName="Report", fontSize=9, fillColor=INK))
        story.append(chart)
    checks = assessment.get("checks", [])
    for category in dict.fromkeys(c.get("category", "") for c in checks):
        rows = []
        for check in checks:
            if check.get("category", "") != category:
                continue
            result = "Erfüllt" if check.get("passed") is True else "Nicht erfüllt" if check.get("passed") is False else "Nicht vorhanden"
            detail = check.get("detail", "")
            for key in ("value", "score", "weight", "weight_pct", "severity"):
                if key in check:
                    detail += f"\n{label(key)}: {value(check[key])}"
            rows.append([check.get("label", ""), result, detail])
        story.extend([paragraph(label(category) or "Kriterien", HEADING),
                      table(["Kriterium", "Bewertung", "Wert / Erläuterung"], rows, [132, 90, WIDTH - 222])])
    for key in ("metrics", "earnings", "drivers", "warnings", "chart_signals", "chart_signal_states", "data_quality"):
        if assessment.get(key):
            add_data(story, label(key), assessment[key])


def add_chart(story, prices):
    points = [p for p in prices.get("points", []) if isinstance(p.get("close"), (int, float)) and math.isfinite(p["close"])]
    if len(points) < 2:
        return
    story.append(paragraph("Kursverlauf · Schlusskurse", HEADING))
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
            story.extend([paragraph(title, HEADING), picture])
        except Exception:
            story.append(paragraph(f"{title}: gespeichertes Bild nicht darstellbar.", SMALL))


def render_report(report: InvestmentReport) -> bytes:
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

    story = [paragraph(report.name, TITLE), paragraph(
        " · ".join(filter(None, [report.ticker, report.isin, "Trade-Report" if report.trade_id else "Aktien-Report"])), SMALL)]
    assessment = report.assessment
    close = report.prices.get("last_close")
    if close is None:
        close = assessment.get("metrics", {}).get("last_close")
    story.append(paragraph(f"{'Historischer Kurs' if report.trade_id else 'Letzter gespeicherter Kurs'}: "
                           f"{value(close)} {report.prices.get('currency') or report.currency} · "
                           f"Datenstand: {report.prices.get('last_date') or assessment.get('as_of') or 'unbekannt'}"))
    for notice in report.notices:
        story.append(paragraph(notice, SMALL))
    add_chart(story, report.prices)
    add_assessment(story, assessment)
    for section in report.sections:
        add_data(story, section.title, section.data)
    if report.journal:
        story.append(paragraph("Handelstagebuch", HEADING))
    for entry in report.journal:
        title = f"{label(entry.get('entry_type', ''))} · {entry.get('trade_date', '')}"
        add_data(story, title, {k: v for k, v in entry.items() if k not in {"market_snapshot", "portfolio_snapshot"}})
        add_data(story, "Position bei Erfassung", entry.get("portfolio_snapshot", {}))
        add_data(story, "Marktumfeld bei Erfassung", entry.get("market_snapshot", {}))
        snapshot = entry.get("stock_snapshot", {})
        # Main historical assessment is already printed for the selected trade.
        if entry.get("id") != report.trade_id:
            add_assessment(story, snapshot.get("assessment", snapshot), f"Bewertung bei {title}")
        for key in ("fundamentals", "institutional_13f", "relative_strength"):
            if snapshot.get(key) and entry.get("id") != report.trade_id:
                add_data(story, label(key), snapshot[key])
        add_images(story, entry.get("chart_images", {}))
    story.append(Spacer(1, 12))
    story.append(paragraph("Datenbasis: gespeicherte Dashboard-Daten und bestehende Bewertungsregeln. "
                           "Fehlende Werte werden nicht geschätzt. Kurswährung und Positionswährung können abweichen. "
                           "Der Export verändert keine Positionen oder Verkaufssignale.", SMALL))
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return output.getvalue()
