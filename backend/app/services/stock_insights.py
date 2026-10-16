"""Read-only provenance, archived score changes and hypothetical weighting."""
from datetime import date
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models import DailyStockOpportunity, StockAssessmentSnapshot
from app.repositories import prices, fundamentals, relative_strength, sec13f
from app.services.assessment_version import calculation_identity
from app.services.stocks import _assessment_score_weights
from app.services.market_calendar import previous_us_market_session_date


def provenance(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    fields, errors = [], []
    def read(key, callback):
        try:
            return callback()
        except Exception:
            errors.append(key)
            return None
    bars = read("prices", lambda: prices.list_price_bars(ticker))
    if bars:
        bar = bars[-1]
        fields.append(dict(key="close", label="Letzter gespeicherter Kurs", value=bar.close, unit="Kurswährung",
            source=bar.source, observation_date=bar.date.isoformat(), retrieved_at=bar.fetched_at.isoformat() if bar.fetched_at else None,
            period=None, formula="Unveränderter gespeicherter Schluss-/Tageskurs; keine Währungsumrechnung."))
    fundamental = read("fundamentals", lambda: fundamentals.get_latest_fundamentals(ticker))
    for key, label, formula in [
        ("quarterly_eps_growth_pct", "EPS-Wachstum Quartal", "Veränderung gegenüber demselben Vorjahresquartal."),
        ("annual_eps_growth_pct", "EPS-Wachstum Jahr", "Veränderung gegenüber dem Vorjahr."),
        ("quarterly_revenue_growth_pct", "Umsatzwachstum Quartal", "Veränderung gegenüber demselben Vorjahresquartal."),
        ("roe_pct", "Eigenkapitalrendite", "Gespeicherte Ergebnis-/Eigenkapitalberechnung."),
        ("profit_margin_pct", "Gewinnmarge", "Gespeichertes Verhältnis von Ergebnis zu Umsatz."),
        ("beta", "Beta", "Gespeicherte Anbieter- oder lokale Benchmarkschätzung."),
    ]:
        metadata = fundamental.metadata_json or {} if fundamental else {}
        fields.append(dict(key=key, label=label, value=getattr(fundamental, key, None), unit="Faktor" if key == "beta" else "%",
            source=(metadata.get("data_sources") or {}).get(key) or (fundamental.source if fundamental else None),
            observation_date=fundamental.as_of.isoformat() if fundamental else None, period=fundamental.fiscal_period if fundamental else None,
            retrieved_at=metadata.get("retrieved_at") or metadata.get("fetched_at"), formula=formula))
    rs = read("rs", lambda: relative_strength.get_latest_rs_rating(ticker))
    fields.append(dict(key="rs", label="RS-Rating", value=rs.rating if rs else None, unit="Rating", source=rs.source if rs else None,
        observation_date=rs.date.isoformat() if rs else None, period=None, retrieved_at=None,
        formula=f"{rs.method}; Vergleichsmenge {rs.universe_size}" if rs else "Keine gespeicherte Ratinggrundlage."))
    institutional = read("institutional", lambda: sec13f.get_latest_trend_for_ticker(ticker))
    profile = read("profile", lambda: fundamentals.get_instrument_profile(ticker)) or {}
    meta = profile.get("metadata") or {}
    ipo = str(meta.get("ipo_date") or meta.get("ipoDate") or "")
    cause = "available" if institutional else "not_yet_classified"
    if not institutional and not meta.get("cusip") and not meta.get("sec13f_cusip"):
        cause = "identifier_unverified"
    fields.append(dict(key="13f", label="13F-Halter", value=institutional.holders_count if institutional else None, unit="Halter",
        source="SEC Form 13F" if institutional else None, observation_date=None,
        period=institutional.report_period.isoformat() if institutional else None,
        retrieved_at=None, publication_date=institutional.filing_date.isoformat() if institutional and institutional.filing_date else None,
        formula="Aggregierte gespeicherte SEC-Meldungen zur Berichtsperiode; kein heutiger vollständiger Besitzstand."))
    return dict(ticker=ticker, fields=fields, component_errors=errors,
        institutional=dict(status="available" if institutional else "missing", missing_cause=cause, ipo_date=ipo or None,
            note="Fehlend bedeutet nicht null institutionelle Halter. Ungeklärte Zuordnungen werden nicht geschätzt."),
        calculation=calculation_identity(_assessment_score_weights()),
        notes=["Berichtsperiode, Beobachtungsdatum und Abrufzeit beschreiben unterschiedliche Zeitpunkte.",
               "Nicht gespeicherte Veröffentlichungs-/Abrufzeiten bleiben unbekannt. 13F enthält keine vollständige Nettopositionierung."])


def score_history(ticker: str) -> dict:
    with SessionLocal() as db:
        rows = list(db.scalars(select(DailyStockOpportunity).where(DailyStockOpportunity.ticker == ticker.upper()).order_by(DailyStockOpportunity.as_of.desc()).limit(63)).all())
    result = [dict(as_of=row.as_of.isoformat(), generated_at=row.generated_at.isoformat() if row.generated_at else None,
        score=row.overall_score, rs=row.rs_rating, calculation=(row.details_json or {}).get("calculation"),
        evidence=(row.details_json or {}).get("assessment_evidence")) for row in rows]
    changes, component_changes, rounding_delta, status = [], [], None, "missing"
    if len(rows) >= 2 and previous_us_market_session_date(rows[0].as_of) == rows[1].as_of:
        current, previous = result[:2]
        if not current["evidence"] or not previous["evidence"] or not (current["calculation"] or {}).get("configuration_hash") or not (previous["calculation"] or {}).get("configuration_hash"):
            status = "legacy_without_criteria"
        elif (current["calculation"] or {}).get("configuration_hash") != (previous["calculation"] or {}).get("configuration_hash"):
            status = "model_changed"
        elif current["evidence"].get("available_weight") != previous["evidence"].get("available_weight") or {key: (item.get("score") is not None, item.get("effective_weight")) for key, item in (current["evidence"].get("components") or {}).items()} != {key: (item.get("score") is not None, item.get("effective_weight")) for key, item in (previous["evidence"].get("components") or {}).items()}:
            status = "coverage_changed"
        else:
            status = "comparable"
            current_components = current["evidence"].get("components") or {}
            previous_components = previous["evidence"].get("components") or {}
            for key, component in current_components.items():
                before = previous_components.get(key) or {}
                if component.get("score") is not None and before.get("score") is not None:
                    delta = component["score"] * component.get("effective_weight", 0) - before["score"] * before.get("effective_weight", 0)
                    component_changes.append(dict(key=key, before=before["score"], after=component["score"], contribution_delta=round(delta, 4)))
            rounding_delta = round(current["score"] - previous["score"] - sum(item["contribution_delta"] for item in component_changes), 4)
            old = {check.get("id") or check["label"]: check for check in previous["evidence"].get("checks", [])}
            for check in current["evidence"].get("checks", []):
                before = old.get(check.get("id") or check["label"])
                if before and before.get("passed") != check.get("passed"):
                    changes.append(dict(id=check.get("id"), label=check["label"], before=before["passed"], after=check["passed"], detail=check.get("detail", "")))
    elif len(rows) >= 2:
        status = "session_gap"
    chronological = list(reversed(result))
    for index, point in enumerate(chronological):
        before = chronological[index - 1] if index else None
        point["connect_to_previous"] = bool(before and (point["calculation"] or {}).get("configuration_hash") and point["calculation"] == before["calculation"] and previous_us_market_session_date(date.fromisoformat(point["as_of"])) == date.fromisoformat(before["as_of"]) and (point["evidence"] or {}).get("available_weight") == (before["evidence"] or {}).get("available_weight"))
    return dict(ticker=ticker.upper(), status=status, points=chronological, changes=changes, component_changes=component_changes, rounding_delta=rounding_delta,
        score_delta=rows[0].overall_score - rows[1].overall_score if status == "comparable" else None,
        note="Vergleich tatsächlich gespeicherter aufeinanderfolgender US-Handelstage. Frühere Kriterien werden nicht aus heutigen Daten erfunden.")


def weight_preview(weights: dict) -> dict:
    from app.domain.stocks.assessment import _weighted_score
    with SessionLocal() as db:
        rows = db.execute(select(StockAssessmentSnapshot.ticker, StockAssessmentSnapshot.name, StockAssessmentSnapshot.overall_score,
            StockAssessmentSnapshot.item_json["overall_v2"], StockAssessmentSnapshot.item_json["calculation"])).all()
    current = calculation_identity(_assessment_score_weights())
    eligible = [(ticker, name, score, payload) for ticker, name, score, payload, identity in rows if payload and payload.get("components") and identity and identity.get("configuration_hash") == current["configuration_hash"]]
    original = sorted(eligible, key=lambda row: ((row[3].get("available_weight") or 0) < 1, -row[2], row[0]))
    ranks = {row[0]: index + 1 for index, row in enumerate(original)}
    compared = []
    for ticker, name, score, payload in eligible:
        alternative = _weighted_score(payload["components"], weights)
        compared.append(dict(ticker=ticker, name=name, current_score=score, alternative_score=alternative["score"],
            coverage=alternative["available_weight"], previous_rank=ranks[ticker]))
    compared.sort(key=lambda row: (row["coverage"] < 1, -(row["alternative_score"] if row["alternative_score"] is not None else -1), row["ticker"]))
    for index, row in enumerate(compared):
        row.update(rank=index + 1, rank_change=row["previous_rank"] - index - 1)
    return dict(weights=weights, rows=compared[:100], count=len(compared), excluded=len(rows) - len(eligible),
        current_configuration=current["configuration_hash"], note="Hypothetischer Vergleich auf unveränderten Teil-Scores derselben Berechnungsversion. Keine Speicherung und keine Änderung der Strategie. Top 100 der Alternative; Rangänderung über alle vergleichbaren Aktien.")
