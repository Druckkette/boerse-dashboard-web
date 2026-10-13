"""Informational context per the user's criterion instructions, 13 Oct 2026.

Never computes, changes or recommends a trend phase. Scores are descriptions,
not return probabilities, portfolio exposure targets or trading gates.
"""

from collections.abc import Sequence
from math import isfinite
from app.domain.market.ampel import TrendAmpelPoint

CONTEXT_SCORE_VERSION = "market_context_v1"


def finite(v):
    return isinstance(v, (int, float)) and isfinite(v)


def band(score):
    if score is None:
        return "Nicht bewertbar", "neutral"
    return (
        ("Konstruktiv", "good")
        if score >= 65
        else ("Gemischt", "warning")
        if score >= 40
        else ("Schwach", "bad")
    )


def criterion(id, label, weight, score, value, rule, explanation="", *, applicable=True):
    evaluation = (
        "not_applicable"
        if not applicable
        else "info"
        if weight == 0 and value != "Nicht verfügbar"
        else "rated"
        if weight > 0 and finite(score)
        else "missing"
    )
    return dict(
        id=id,
        label=label,
        weight=weight,
        score=round(min(100, max(0, score)), 2) if finite(score) else None,
        contribution=None,
        evaluation=evaluation,
        value=value,
        rule=rule,
        explanation=explanation,
    )


def subscore(key, label, weight, criteria, *, neutral=None):
    rated = [c for c in criteria if c["weight"] > 0 and c["evaluation"] == "rated"]
    missing = [c for c in criteria if c["weight"] > 0 and c["evaluation"] == "missing"]
    known = sum(c["weight"] for c in rated)
    total = known + sum(c["weight"] for c in missing)
    score = sum(c["weight"] * c["score"] for c in rated) / known if known else neutral
    for c in rated:
        c["contribution"] = round(c["weight"] * c["score"] / known, 2)
    score = round(score, 2) if score is not None else None
    status, tone = band(score)
    return dict(
        key=key,
        label=label,
        weight=weight,
        score=score,
        status=status,
        tone=tone,
        data_status="missing" if score is None else "partial" if missing else "complete",
        coverage_pct=round(100 * known / total, 1) if total else (100 if score is not None else 0),
        criteria=criteria,
    )


def category(key, title, scope, subscores, message=""):
    rated = [s for s in subscores if s["weight"] and s["score"] is not None]
    known = sum(s["weight"] for s in rated)
    score = sum(s["weight"] * s["score"] for s in rated) / known if known else None
    score = round(score, 2) if score is not None else None
    status, tone = band(score)
    coverage = sum(s["weight"] * s["coverage_pct"] for s in subscores) / sum(
        s["weight"] for s in subscores
    )
    # A small isolated component (e.g. W14 alone) cannot represent a whole
    # category whose primary observations are missing. This is availability,
    # never a negative market contribution or a trend-phase gate.
    if coverage < 50:
        score = None
        status, tone = band(None)
    return dict(
        key=key,
        title=title,
        scope=scope,
        score=score,
        status=status,
        tone=tone,
        data_status="missing"
        if score is None
        else "partial"
        if any(s["weight"] and s["data_status"] != "complete" for s in subscores)
        else "complete",
        coverage_pct=round(coverage, 1),
        subscores=subscores,
        message=message,
    )


def confirmed_warning(triggers, *, enter=2, leave=2):
    active, on, off = False, 0, 0
    for trigger in triggers:
        if trigger is None:
            active, on, off = False, 0, 0
            continue
        on = on + 1 if trigger else 0
        off = off + 1 if not trigger else 0
        if not active and on >= enter:
            active = True
        elif active and off >= leave:
            active = False
    return None if not triggers or triggers[-1] is None else 0 if active else 100


def _window_valid(points, index, size, volume=False):
    window = points[max(0, index - size + 1) : index + 1]
    return len(window) == size and all(
        p.price_data_complete
        and finite(p.close)
        and (not volume or finite(p.volume) and p.volume > 0)
        for p in window
    )


def index_score(points: Sequence[TrendAmpelPoint]):
    p = points[-1] if points else None

    def warn(id, label, w, fn, size, rule, value, volume=False):
        triggers = [
            bool(fn(x, i)) if _window_valid(points, i, size, volume) else None
            for i, x in enumerate(points)
        ]
        return criterion(
            id,
            label,
            w,
            confirmed_warning(triggers),
            value if triggers and triggers[-1] is not None else "Nicht verfügbar",
            rule,
            "Eintritt/Austritt nach 2 vollständigen Sitzungen. Fehlende Werte unterbrechen die Bestätigung.",
        )

    selling = [
        warn(
            "W01",
            "Bärische Umkehrungen",
            1,
            lambda x, i: x.neg_reversals_10d >= 3,
            10,
            "Mindestens 3 negative Umkehrungen in 10 Sitzungen.",
            f"{p.neg_reversals_10d} / 10T" if p else "",
        ),
        warn(
            "W03",
            "Stau-Tage",
            0.5,
            lambda x, i: sum(bool(a.is_stall) for a in points[max(0, i - 9) : i + 1]) >= 3,
            60,
            "Mindestens 3 Stau-Tage in 10 Sitzungen; vollständige Volumen-SMA50.",
            f"{sum(bool(x.is_stall) for x in points[-10:])} / 10T",
            True,
        ),
        warn(
            "W04",
            "Distributionstage",
            0.5,
            lambda x, i: x.dist_count_25 >= 4,
            75,
            "Mindestens 4 aktive Distributionstage in 25 Sitzungen; V2-Gewicht 0,5.",
            f"{p.dist_count_25} / 25T" if p else "",
            True,
        ),
    ]
    demand = [
        warn(
            "W02",
            "Schlussqualität",
            1,
            lambda x, i: x.low_cr_5d >= 3,
            5,
            "Mindestens 3 Schlüsse im unteren Viertel der Tagesrange in 5 Sitzungen.",
            f"{p.low_cr_5d} / 5T" if p else "",
        ),
        warn(
            "W05",
            "Verlust-/Gewinntage",
            0.5,
            lambda x, i: x.loss_days_10d > x.gain_days_10d and (x.loss_gain_ratio_10d or 0) >= 1.5,
            11,
            "Verlusttage überwiegen; Verhältnis mindestens 1,5 in 10 Sitzungen.",
            f"{p.loss_days_10d}:{p.gain_days_10d}" if p else "",
        ),
        warn(
            "W11",
            "Nachlassendes Volumen",
            0.5,
            lambda x, i: x.up_vol_declining,
            6,
            "Kurs steigt über 5 Sitzungen, mittlere Volumenänderung fällt.",
            "Abnehmend" if p and p.up_vol_declining else "Keine Häufung",
            True,
        ),
    ]
    known = bool(p and p.price_data_complete)
    trend = [
        criterion(
            "A09",
            "Aufwärtstrend bestätigt",
            1,
            100 if known and p.phase == "aufwaertstrend" else 50 if known else None,
            p.phase if known else "Nicht verfügbar",
            "Bestätigter Aufwärtstrend gibt Bonus; andere Phasen sind neutral.",
            "Aufwärtsstruktur = bestätigte höhere Swing-Hochs und höhere Swing-Tiefs. Ein Pivot wird erst nach einer Gegenbewegung von 1,5 ATR bestätigt; keine zukünftigen Kerzen. A19 prüft den Bruch des gespeicherten höheren Tiefs.",
        ),
        criterion(
            "A11",
            "FTD negiert",
            1,
            0 if known and p.ftd_negated else 100 if known else None,
            "Negiert"
            if known and p.ftd_negated
            else "Nicht negiert"
            if known
            else "Nicht verfügbar",
            "Negation gibt Malus in diesem Informationsscore. Die Trendampel behält ihre eigenen Regeln.",
        ),
    ]
    display = [
        criterion(id, label, 0, None, value, rule)
        for id, label, value, rule in [
            (
                "W06",
                "Abstand zur 50-SMA",
                _format(p.dist_50sma_pct if p else None, "%"),
                "Nur Anzeige; Überdehnung über 5%, Nasdaq über 7%.",
            ),
            (
                "W07",
                "Schluss zur 21-EMA",
                _held(p.ema21_held if p else None),
                "Gewicht 0; bereits in Trendampel.",
            ),
            (
                "W08",
                "Abstand zur 21-EMA",
                _format(p.dist_21ema if p else None, " ATR"),
                "Überdehnung über 3 ATR; nur Anzeige, kein Malus.",
            ),
            (
                "W09",
                "Schluss zur 50-SMA",
                _held(p.sma50_held if p else None),
                "Gewicht 0; bereits in Trendampel.",
            ),
            (
                "W10",
                "Schluss zur 200-SMA",
                _held(p.sma200_held if p else None),
                "Gewicht 0; bereits in Trendampel.",
            ),
            (
                "W12",
                "Intermarket-Divergenz",
                "Siehe bisherigen Intermarket-Block",
                "Nur Anzeige; keine zweite Marktbreitengewichtung.",
            ),
            (
                "W13",
                "Defensive Rotation",
                "Siehe bisherigen Sektorrotations-Block",
                "Nur Anzeige. Sektordaten werden für keinen Score benötigt.",
            ),
            (
                "W14",
                "Erholungsquote",
                "Gewichtet bei Marktbreite",
                "Zuordnung nach Excel; hier kein zweiter Beitrag.",
            ),
        ]
    ]
    return category(
        "index",
        "Index",
        "Ausgewählter Index",
        [
            subscore("selling", "Verkaufsdruck", 45, selling),
            subscore("demand", "Schlussqualität & Nachfrage", 35, demand),
            subscore("confirmation", "Trendbestätigung", 20, trend),
            subscore("info", "Weitere Indexmerkmale", 0, display),
        ],
        "MA-Brüche, Überdehnung, Intermarket und Rotation bleiben ohne Gewicht. W14 wird bei Marktbreite gewichtet.",
    )


def _held(v):
    return "Oberhalb" if v is True else "Unterhalb" if v is False else "Nicht verfügbar"


def _format(v, suffix=""):
    return f"{v:.2f}{suffix}" if finite(v) else "∞" if v == float("inf") else "Nicht verfügbar"


def _ratio(rows, numerator, denominator):
    if not rows or any(
        not finite(r.get(numerator)) or not finite(r.get(denominator)) for r in rows
    ):
        return None
    n, d = sum(r[numerator] for r in rows), sum(r[denominator] for r in rows)
    return n / d if d > 0 else float("inf") if n > 0 else None


def ratio_score(v):
    if v is None:
        return None
    return 100 if v >= 2 else 75 if v >= 1.5 else 60 if v >= 1 else 40 if v >= 0.8 else 0


def breadth_score(points, rows, *, ad_divergence=None):
    p = rows[-1] if rows else {}
    participation = [
        criterion(
            id,
            label,
            w,
            p.get(col),
            _format(p.get(col), "%"),
            "Anteil 0–100% entspricht Score 0–100. Keine zusätzliche Farbstufe gewichtet.",
        )
        for id, label, w, col in [
            ("B01", "Aktien über 50-SMA", 1, "pct_above_50sma"),
            ("B02", "Aktien über 200-SMA", 1, "pct_above_200sma"),
            ("B11", "Aktien über 20-SMA", 0.5, "pct_above_20sma"),
        ]
    ]
    mcc = p.get("mcclellan")
    ms = (
        (
            100
            if mcc > 125
            else 90
            if mcc > 80
            else 80
            if mcc > 50
            else 65
            if mcc > 0
            else 50
            if mcc == 0
            else 35
            if mcc > -50
            else 20
            if mcc > -80
            else 5
            if mcc > -125
            else 0
        )
        if finite(mcc)
        else None
    )
    momentum = [
        criterion(
            "D07",
            "McClellan-Stufen",
            1,
            ms,
            _format(mcc),
            "Stufen: >125→100; >80→90; >50→80; >0→65; 0→50; >−50→35; >−80→20; >−125→5; sonst 0.",
        ),
        criterion(
            "B03",
            "McClellan negativ",
            0,
            None,
            _format(mcc),
            "Über D07 einmal gewichtet, kein zweiter Beitrag.",
        ),
    ]
    ratio_rule = "Summe über Fenster: <0,8→0; 0,8–<1→40; 1–<1,5→60; 1,5–<2→75; ≥2→100. Beide Summen 0: nicht bewertbar."

    def ratios(id, label, w, n, d, days, rule=ratio_rule):
        v = _ratio(rows[-days:] if len(rows) >= days else [], n, d)
        return criterion(id, label, w, ratio_score(v), _format(v), rule)

    ad = [
        ratios("B04", "A/D-Verhältnis (3T)", 0.5, "advancers", "decliners", 3),
        criterion(
            "D02",
            "A/D-Linie bestätigt Index",
            0.25,
            0 if ad_divergence else 100 if ad_divergence is False else None,
            "Divergenz"
            if ad_divergence
            else "Keine Divergenz"
            if ad_divergence is False
            else "Nicht verfügbar",
            "Index nahe vorherigem 20T-Hoch (99,8%); A/D unter exaktem vorherigem Maximum. 3 Tage Eintritt/2 Austritt; kein prozentualer Puffer auf negativer A/D-Linie.",
        ),
    ]
    highs = [
        ratios("B05", "Neue Hochs/Tiefs (3T)", 1, "new_highs", "new_lows", 3),
        ratios(
            "B10",
            "Neue Hochs/Tiefs (20T)",
            0.5,
            "new_highs",
            "new_lows",
            20,
            ratio_rule
            + " Einzelaktien-Hoch/Tief aus bestehender 20T-Berechnung; gemeinsamer Unterscore mit B05.",
        ),
        criterion(
            "D08",
            "NH/NL-Farbstufe",
            0,
            None,
            _format(p.get("nh_nl_ratio")),
            "Nur Anzeige; keine dritte Gewichtung derselben Daten.",
        ),
    ]
    volume = [
        ratios(
            "D03",
            "Up/Down-Volumen (3T)",
            0.25,
            "up_volume",
            "down_volume",
            3,
            ratio_rule + " Volumen der Universe-Aktien, keine ETF-Ersatzdaten.",
        )
    ]
    deemer = _ratio(rows[-10:] if len(rows) >= 10 else [], "advancers", "decliners")
    ds = (
        (100 if deemer >= 1.97 else 75 if deemer >= 1.5 else 50 if deemer >= 1 else 25)
        if deemer is not None
        else None
    )
    thrust = [
        criterion(
            "D04",
            "Deemer Ratio",
            0.25,
            ds,
            _format(deemer),
            "10T-Summen: ≥1,97→100; ≥1,5→75; ≥1→50; darunter 25. Kein zweiter Rückblickbonus.",
        )
    ]
    clean = (
        list(points[-60:])
        if len(points) >= 60
        and all(x.price_data_complete and finite(x.close) for x in points[-60:])
        else []
    )
    recovery = None
    if len(clean) >= 60:
        recent = clean[-60:]
        hi = max(range(60), key=lambda i: recent[i].close)
        high, low = recent[hi].close, min(x.close for x in recent[hi:])
        if high > low and (high - low) / high > 0.05 and 60 - hi >= 5:
            recovery = max(0, (recent[-1].close - low) / (high - low) * 100)
    rs = min(100, recovery) if recovery is not None else 100 if len(clean) >= 60 else None
    rec = [
        criterion(
            "W14",
            "Erholungsquote",
            0.5,
            rs,
            _format(recovery, "%")
            if recovery is not None
            else "Keine relevante Korrektur"
            if len(clean) >= 60
            else "Nicht verfügbar",
            "(Schluss−Korrekturtief)/(Korrekturhoch−Korrekturtief)×100 im kausalen 60T-Fenster. Erst nach >5% Rückgang und ≥5 Sitzungen seit Hoch; sonst kein Malus.",
            "Indexerholung, nach deiner Excel der Marktbreite zugeordnet. Keine Messung der Anzahl teilnehmender Aktien.",
        )
    ]
    display = [
        criterion(id, label, 0, None, value, rule)
        for id, label, value, rule in [
            (
                "B06",
                "Datenabdeckung",
                _format(p.get("coverage_pct"), "%"),
                "Nur Datenhinweis, kein Marktmalus.",
            ),
            (
                "B09",
                "Interne Breitenphase",
                "Siehe bisherigen Breitenblock",
                "Legacy-Diagnose aus Warnzahl/MA-Anteilen; keine zweite Trendampel.",
            ),
            (
                "D01",
                "Russell vs. S&P",
                "Siehe bisherigen Vergleich",
                "Nur bisherige Anzeige; kein Gewicht.",
            ),
            (
                "D05",
                "Breitenschub-Rückblick",
                "Siehe Deemer-Block",
                "Historisches Ereignis, kein zweiter Bonus neben D04.",
            ),
            (
                "D06",
                "50-SMA-Breitendivergenz",
                "Siehe MA-Teilnahme",
                "Dieselbe MA-Basis; kein zweiter Malus.",
            ),
            ("D09", "MA-Farbstufen", "Siehe MA-Teilnahme", "Nur Anzeige."),
        ]
    ]
    return category(
        "breadth",
        "Marktbreite",
        "US-Aktienuniversum; W14: gewählter Index",
        [
            subscore("participation", "Trendteilnahme", 30, participation),
            subscore("momentum", "Breitenmomentum", 20, momentum),
            subscore("ad", "Advance/Decline", 15, ad),
            subscore("highs", "Neue Hochs & Tiefs", 20, highs),
            subscore("volume", "Volumenbreite", 5, volume),
            subscore("thrust", "Breitenschub", 5, thrust),
            subscore("recovery", "Erholungskontext", 5, rec),
            subscore("info", "Zusätzliche Anzeigen", 0, display),
        ],
        "W14 beschreibt die Indexerholung. Coverage, Russell-Vergleich, Farb- und Rückblicksignale bleiben ohne Zusatzgewicht.",
    )


def powertrend_score(points, *, enabled):
    p = points[-1] if points else None
    state = p.powertrend_state if p and enabled and p.price_data_complete else None
    status = [
        criterion(
            "P05",
            "Powertrend aktiv",
            1,
            100 if state == "on" else 50 if state is not None else None,
            state or "Nicht verfügbar",
            "ON gibt Bonus (100); sonst neutral (50). Kein Einfluss auf die Ampel.",
        ),
        criterion(
            "P06",
            "Powertrend unter Druck",
            2,
            0 if state == "under_pressure" else 50 if state is not None else None,
            state or "Nicht verfügbar",
            "Druck gibt Malus (0); sonst neutral (50). Gewicht2, keine zweite Belastung aus P02.",
        ),
    ]
    requirements = (
        [
            p.powertrend_low_above_21_streak >= 10,
            p.powertrend_ema21_over_50_streak >= 5,
            bool(p.powertrend_sma50_rising_1d),
            bool(p.powertrend_positive_or_flat_day),
        ]
        if p
        else []
    )
    progress = [
        criterion(
            "P01",
            "Startbedingungen",
            1,
            100 if state == "on" else 25 * sum(requirements) if state is not None else None,
            f"{sum(requirements)}/4" if state is not None else "Nicht verfügbar",
            "10 Tiefs über21-EMA;5 Tage EMA21>50-SMA; SMA50 steigt; Tag positiv/flat. Vorbereitung aktiviert PT nicht vorzeitig.",
            "Bei ON bleibt der Unterscore100: der Verlust einzelner Startbedingungen beendet den formalen Powertrend nicht.",
            applicable=state != "under_pressure",
        ),
        criterion(
            "P03",
            "Erholungsbedingungen",
            1,
            25 * sum(requirements) if state == "under_pressure" else None,
            f"{sum(requirements)}/4" if state == "under_pressure" else "Nicht verfügbar",
            "Rückkehr erst, wenn erneut alle vier Startbedingungen erfüllt sind.",
            applicable=state in (None, "under_pressure"),
        ),
        criterion(
            "P02",
            "Druckdefinition",
            0,
            None,
            "3 Schlüsse unter21 oder deutlicher50-Bruch",
            "Formal aktiv bis definierter Endbedingung; Druck ist eigener Zustand.",
        ),
        criterion(
            "P04",
            "Formales Ende",
            0,
            None,
            (p.powertrend_reason or "Kein aktuelles Endsignal")
            if p and state is not None
            else "Nicht verfügbar",
            "21-EMA<50-SMA. Verlust einer Startbedingung allein beendet PT nicht.",
        ),
    ]
    return category(
        "powertrend",
        "Powertrend",
        "Ausgewählter Index; ausschließlich IBD",
        [
            subscore("state", "Bestätigter Status", 70, status),
            subscore("progress", "Start & Erholung", 30, progress),
        ],
        "Formaler Status und Vorbereitung bleiben getrennt. Vier erfüllte Bedingungen ersetzen keine bestätigte Aktivierung.",
    )


def equal_weight_score(summary):
    valid = summary.get("source") == "database"
    mode = summary.get("mode") if valid else None
    streak = summary.get("candidate_streak", 0)
    modes = [
        criterion(
            "E01",
            "Equal Weight Rückenwind",
            0.5,
            100 if mode == "rueckenwind" else 50 if mode is not None else None,
            mode or "Nicht verfügbar",
            "Schlechterer52W-Abstand höchstens4%,3 Sitzungen bestätigt:100; sonst neutral50.",
        ),
        criterion(
            "E03",
            "Equal Weight Schutz",
            1.5,
            0 if mode == "schutz" else 50 if mode is not None else None,
            mode or "Nicht verfügbar",
            "Schlechterer52W-Abstand über8%,3 Sitzungen bestätigt:0; sonst neutral50. Kein Gate.",
        ),
        criterion(
            "E02",
            "Equal Weight Wachsam",
            0,
            None,
            mode or "Nicht verfügbar",
            "4–8% Abstand: neutraler Score50, kein zusätzlicher Strafbeitrag.",
        ),
    ]
    confirmation = [
        criterion(
            "E04",
            "Bestätigung",
            1,
            100 if valid and streak >= 3 else 50 if valid else None,
            f"{streak}/3 Sitzungen" if valid else "Nicht verfügbar",
            "Drei gemeinsame abgeschlossene Sitzungen im selben Kandidatenmodus; bisheriger Zustand bleibt bis neuer Bestätigung gültig.",
            "Schluss relativ zum höchsten Hoch der letzten252 Sitzungen; volle Historie erforderlich. Bestätigung verhindert Umschaltung durch einzelne Tagesausschläge.",
        )
    ]
    return category(
        "equal_weight",
        "Equal Weight",
        "RSP & QQEW, US-weit",
        [
            subscore(
                "mode",
                "Bestätigter Breitenzustand",
                80,
                modes,
                neutral=50 if mode == "wachsam" else None,
            ),
            subscore("confirmation", "Bestätigung & Stabilität", 20, confirmation),
        ],
        "Schlechterer RSP/QQEW-Abstand bestimmt den Zustand. Bestätigung ist Vertrauensinformation, kein unabhängiger Marktbonus.",
    )


def volatility_score(point, *, vix_valid=False, vxx_valid=False):
    vix = point.vix_regime if point and vix_valid else None
    vxx = point.vxx_state if point and vxx_valid else None
    regime = point.vol_regime if point and vix_valid and vxx_valid else None

    def choice(id, label, w, value, selected, score, valid, rule):
        return criterion(
            id,
            label,
            w,
            score if value == selected else 50 if valid else None,
            value or "Nicht verfügbar",
            rule + " Inaktiver Zustand ist neutral50.",
        )

    vixchecks = [
        choice(
            "V01",
            "VIX Stress",
            1,
            vix,
            "Stress",
            0,
            vix_valid,
            "Nur VIX-Unterscore; kein hartes Gate.",
        ),
        choice("V02", "VIX ruhig", 1, vix, "Ruhig", 100, vix_valid, "Nur VIX-Unterscore."),
        criterion(
            "V03",
            "VIX überdehnt",
            0,
            None,
            "Ja"
            if point and vix_valid and point.vix_panic_overextension
            else "Nein"
            if vix_valid
            else "Nicht verfügbar",
            "Über20% über10-SMA; nur Anzeige, kein zusätzlicher Malus.",
        ),
    ]
    vxxchecks = [
        choice(
            "V04",
            "VXX Stress",
            1,
            vxx,
            "Steigend",
            0,
            vxx_valid,
            "Über steigender21-EMA; nur VXX-Unterscore.",
        ),
        choice(
            "V05",
            "VXX Entspannung",
            1,
            vxx,
            "Entspannt",
            100,
            vxx_valid,
            "Unter fallender21-EMA; nur VXX-Unterscore.",
        ),
    ]
    combined = [
        choice(
            id,
            label,
            w,
            regime,
            selected,
            score,
            regime is not None,
            "Genau ein kombiniertes Regime gewichtet; kein Ampel- oder Handlungsgate.",
        )
        for id, label, w, selected, score in [
            ("V07", "Risk Off bestätigt", 3, "Risk Off bestätigt", 0),
            ("V06", "Fragile Rally", 1, "Fragile Rally", 25),
            ("V08", "Kurzer Volatilitätsschock", 1, "Kurzer Volatilitätsschock", 25),
            ("V09", "Risk On / ruhig", 0.5, "Risk On / ruhig", 100),
        ]
    ]
    return category(
        "volatility",
        "Volatilität",
        "VIX/VXX & S&P-Kontext, US-weit",
        [
            subscore("vix", "VIX-Zustand", 40, vixchecks, neutral=50 if vix == "Neutral" else None),
            subscore(
                "vxx", "VXX-Bestätigung", 40, vxxchecks, neutral=50 if vxx == "Gemischt" else None
            ),
            subscore(
                "combined",
                "Gemeinsames Regime",
                20,
                combined,
                neutral=50 if regime == "Neutral" else None,
            ),
        ],
        "VIX/VXX jeweils40%, gemeinsames Regime20%. Ausschließende Zustände werden innerhalb jeder Gruppe einmal bewertet. Risk Off schaltet nur diese Kennzahl.",
    )
