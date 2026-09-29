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
from reportlab.platypus import CondPageBreak, Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

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
    "passed": "Kriterium erfüllt", "active": "Aktiv", "available": "Verfügbar", "score": "Score",
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
    "k4_rs_leadership": "K4 RS Leadership", "k13_rs_dynamics": "K13 RS Dynamics",
    "high_position": "ATH-/52W-High Position", "up_down_volume": "Up/Down Volume",
    "cmf": "CMF / Akkumulation", "fundamental_core": "Fundamental Core",
    "k9_eps_sales_alignment": "K9 EPS/Sales Alignment", "price_action_core": "Price Action Core",
    "k35_down_week_quality": "K35 Down-Week Quality", "k38_hh_hl_good_close": "K38 HH/HL + Good Close",
    "price_above_200_sma": "Kurs > 200 SMA", "price_above_50_sma": "Kurs > 50 SMA",
    "price_above_21_ema": "Kurs > 21 EMA", "price_above_10_sma": "Kurs > 10 SMA",
    "ma_order": "MA-Reihenfolge", "persistence": "MA-Persistenz", "slope": "MA-Richtung",
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
        "available": "Verfügbar", "partial": "Teilweise", "neutral": "Neutral",
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
    overall = assessment.get("overall_v2") or {}
    if overall.get("status") == "limited":
        available_weight = overall.get("available_weight")
        suffix = f" ({value(available_weight * 100)} % Gewichtung verfügbar)" if isinstance(available_weight, (int, float)) else ""
        story.append(paragraph(f"Gesamtbewertung eingeschränkt{suffix}.", SMALL))
    for title, detail in available:
        score = detail.get("score")
        score_text = f"{value(score)} / 100" if isinstance(score, (int, float)) else status_text(detail.get("status"))
        story.extend([CondPageBreak(90), paragraph(f"{title}  ·  {score_text}", HEADING)])
        rows = []
        for key, component in (detail.get("components") or {}).items():
            if not isinstance(component, dict):
                continue
            component_score = component.get("score")
            base = component.get("base_weight")
            effective = component.get("effective_weight")
            weight_bits = []
            if isinstance(base, (int, float)):
                weight_bits.append(f"Basis {value(base * 100)} %")
            if isinstance(effective, (int, float)):
                weight_bits.append(f"effektiv {value(effective * 100)} %")
            rows.append([
                label(key),
                f"{value(component_score)} / 100" if isinstance(component_score, (int, float)) else "–",
                status_text(component.get("status")),
                " · ".join(weight_bits) or "–",
            ])
        if rows:
            story.append(table(["Kriterium", "Score", "Status", "Gewichtung"], rows,
                               [190, 72, 86, WIDTH - 348]))


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
        story.extend([CondPageBreak(90), paragraph(label(category) or "Kriterien", HEADING),
                      table(["Kriterium", "Bewertung", "Wert / Erläuterung"], rows, [132, 90, WIDTH - 222])])
    add_v2_assessment(story, assessment)
    for key in (
        "setup", "eligibility", "metrics", "earnings", "drivers", "warnings",
        "chart_signals", "chart_signal_states", "data_quality",
    ):
        if assessment.get(key):
            add_data(story, label(key), assessment[key])


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
        ("Gesamtscore", f"{value(overall)} / 100" if overall is not None else "–"),
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
        add_data(story, section.title, section.data)
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
                add_data(story, label(key), snapshot[key])
        add_images(story, entry.get("chart_images", {}))
    story.append(Spacer(1, 12))
    story.append(paragraph("Datenbasis: gespeicherte Dashboard-Daten und bestehende Bewertungsregeln. "
                           "Fehlende Werte werden nicht geschätzt. Kurswährung und Positionswährung können abweichen. "
                           "Der Export verändert keine Positionen oder Verkaufssignale.", SMALL))
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return output.getvalue()
