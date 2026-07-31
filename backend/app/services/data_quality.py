from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import FundamentalSnapshot, Instrument, IsinMapping, PriceBar
from app.db.session import SessionLocal
from app.repositories import prices as price_repository
from app.repositories.prices import PriceRepositoryUnavailable
from app.schemas import DataDiagnosticIssue, DataDiagnosticsResponse, DataQualityEvent, PortfolioPosition
from app.services.freshness import get_freshness
from app.services.portfolio import get_portfolio_positions


STALE_POSITION_PRICE_DAYS = 5
IMPLAUSIBLE_GAIN_PCT = 400.0
IMPLAUSIBLE_LOSS_PCT = -75.0


def build_data_diagnostics() -> DataDiagnosticsResponse:
    now = datetime.now(UTC)
    today = now.date()
    freshness = get_freshness().services
    positions = get_portfolio_positions()
    open_tickers = sorted({position.ticker.upper() for position in positions})

    latest_by_ticker: dict[str, date] = {}
    fundamentals_by_ticker: dict[str, date] = {}
    missing_yahoo_tickers: list[str] = []
    ticker_mapping_events: list[DataQualityEvent] = []
    isin_mappings_count = 0
    price_cache_tickers_count = 0
    try:
        with SessionLocal() as db:
            price_cache_tickers_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(Instrument)
                    .where(
                        exists(
                            select(1).where(
                                PriceBar.instrument_id == Instrument.id,
                                PriceBar.close.is_not(None),
                            )
                        )
                    )
                )
                or 0
            )
            if open_tickers:
                latest_price_rows = db.execute(
                    select(Instrument.ticker, func.max(PriceBar.date))
                    .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                    .where(
                        Instrument.ticker.in_(open_tickers),
                        PriceBar.close.is_not(None),
                    )
                    .group_by(Instrument.ticker)
                ).all()
                latest_by_ticker = {
                    str(ticker).upper(): price_date
                    for ticker, price_date in latest_price_rows
                    if ticker and price_date is not None
                }
                fundamental_rows = db.execute(
                    select(FundamentalSnapshot.ticker, func.max(FundamentalSnapshot.as_of))
                    .where(FundamentalSnapshot.ticker.in_(open_tickers))
                    .group_by(FundamentalSnapshot.ticker)
                ).all()
                fundamentals_by_ticker = {
                    str(ticker).upper(): as_of
                    for ticker, as_of in fundamental_rows
                    if ticker and as_of is not None
                }
                instruments = db.scalars(select(Instrument).where(Instrument.ticker.in_(open_tickers))).all()
                mapped = {str(item.ticker).upper(): str(item.yahoo_symbol or "").strip() for item in instruments}
                missing_yahoo_tickers = [ticker for ticker in open_tickers if not mapped.get(ticker)]
                ticker_mapping_events = [
                    DataQualityEvent(
                        ticker=ticker,
                        event_type="ticker_mapping",
                        label="Abweichendes Yahoo-Symbol",
                        detail=f"Gespeicherter Ticker {ticker} wird bei Yahoo als {yahoo_symbol} geladen.",
                        severity="info",
                    )
                    for ticker, yahoo_symbol in mapped.items()
                    if yahoo_symbol and yahoo_symbol.upper() != ticker
                ]
            isin_mappings_count = int(db.scalar(select(func.count()).select_from(IsinMapping)) or 0)
    except SQLAlchemyError as exc:
        return DataDiagnosticsResponse(
            as_of=today.isoformat(),
            generated_at=now,
            health_tone="bad",
            decision_status="blocked",
            summary="Datenbank-Diagnose nicht verfügbar.",
            freshness=freshness,
            issues=[
                DataDiagnosticIssue(
                    key="database_unavailable",
                    label="Datenbank nicht erreichbar",
                    severity="critical",
                    detail=f"{type(exc).__name__}: {exc}",
                    category="system",
                    blocks_decisions=True,
                )
            ],
        )

    stale_before = today - timedelta(days=STALE_POSITION_PRICE_DAYS)
    missing_price_tickers = [ticker for ticker in open_tickers if ticker not in latest_by_ticker]
    stale_price_tickers = [
        ticker for ticker in open_tickers if latest_by_ticker.get(ticker) and latest_by_ticker[ticker] < stale_before
    ]
    missing_fundamentals = [ticker for ticker in open_tickers if ticker not in fundamentals_by_ticker]
    missing_risk_metrics = sorted(
        {
            position.ticker
            for position in positions
            if position.atr_pct is None or position.beta is None or position.beta_balancer_score is None
        }
    )
    missing_stops = [position.ticker for position in positions if position.stop_price is None]
    implausible = [position.ticker for position in positions if _position_is_implausible(position)]
    quality_by_ticker = assess_position_quality(
        positions,
        latest_by_ticker=latest_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
        today=today,
    )
    events = [*_detect_corporate_action_candidates(open_tickers), *ticker_mapping_events][:25]

    issues = _build_issues(
        open_tickers=open_tickers,
        missing_price_tickers=missing_price_tickers,
        stale_price_tickers=stale_price_tickers,
        missing_yahoo_tickers=missing_yahoo_tickers,
        missing_fundamentals=missing_fundamentals,
        missing_risk_metrics=missing_risk_metrics,
        missing_stops=missing_stops,
        implausible=implausible,
        isin_mappings_count=isin_mappings_count,
        freshness=freshness,
        events=events,
    )
    blocked = any(item["status"] == "blocked" for item in quality_by_ticker.values())
    limited = any(item["status"] == "limited" for item in quality_by_ticker.values())
    critical_count = sum(issue.severity == "critical" for issue in issues)
    warning_count = sum(issue.severity == "warning" for issue in issues)
    decision_status = "blocked" if blocked or critical_count else "limited" if limited or warning_count else "trusted"
    health_tone = "bad" if decision_status == "blocked" else "warning" if decision_status == "limited" else "good"
    stop_coverage_count = len(positions) - len(missing_stops)
    stop_coverage_total = len(positions)

    return DataDiagnosticsResponse(
        as_of=today.isoformat(),
        generated_at=now,
        health_tone=health_tone,
        decision_status=decision_status,
        summary=_summary(decision_status, len(open_tickers), critical_count, warning_count),
        open_positions_count=len(open_tickers),
        price_cache_tickers_count=price_cache_tickers_count,
        missing_price_count=len(missing_price_tickers),
        stale_price_count=len(stale_price_tickers),
        missing_yahoo_symbol_count=len(missing_yahoo_tickers),
        isin_mappings_count=isin_mappings_count,
        stop_coverage_count=stop_coverage_count,
        stop_coverage_total=stop_coverage_total,
        stop_coverage_pct=(stop_coverage_count / stop_coverage_total * 100 if stop_coverage_total else 0.0),
        missing_fundamentals_count=len(missing_fundamentals),
        missing_risk_metrics_count=len(missing_risk_metrics),
        implausible_position_count=len(implausible),
        freshness=freshness,
        corporate_events=events,
        issues=issues or [
            DataDiagnosticIssue(
                key="data_ready",
                label="Datenbasis konsistent",
                severity="info",
                detail="Aktualität, Positionswerte, Stopps und Zuordnungen wurden geprüft.",
                category="system",
            )
        ],
    )


def get_position_quality_by_ticker() -> dict[str, dict[str, str]]:
    positions = get_portfolio_positions()
    latest_by_ticker: dict[str, date] = {}
    fundamentals_by_ticker: dict[str, date] = {}
    for position in positions:
        ticker = position.ticker.upper()
        try:
            latest = price_repository.get_latest_price_bar_date(ticker)
        except PriceRepositoryUnavailable:
            latest = None
        if latest is not None:
            latest_by_ticker[ticker] = latest
    try:
        with SessionLocal() as db:
            tickers = [position.ticker.upper() for position in positions]
            if tickers:
                rows = db.execute(
                    select(FundamentalSnapshot.ticker, func.max(FundamentalSnapshot.as_of))
                    .where(FundamentalSnapshot.ticker.in_(tickers))
                    .group_by(FundamentalSnapshot.ticker)
                ).all()
                fundamentals_by_ticker = {
                    str(ticker).upper(): as_of for ticker, as_of in rows if ticker and as_of is not None
                }
    except SQLAlchemyError:
        fundamentals_by_ticker = {}
    return assess_position_quality(
        positions,
        latest_by_ticker=latest_by_ticker,
        fundamentals_by_ticker=fundamentals_by_ticker,
        today=date.today(),
    )


def assess_position_quality(
    positions: list[PortfolioPosition],
    *,
    latest_by_ticker: dict[str, date],
    fundamentals_by_ticker: dict[str, date],
    today: date,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    stale_before = today - timedelta(days=STALE_POSITION_PRICE_DAYS)
    for position in positions:
        ticker = position.ticker.upper()
        blockers: list[str] = []
        limitations: list[str] = []
        latest = latest_by_ticker.get(ticker)
        if position.current_price <= 0 or latest is None:
            blockers.append("Kursdaten fehlen")
        elif latest < stale_before:
            limitations.append(f"Kursstand {latest.isoformat()} ist veraltet")
        if _position_is_implausible(position):
            blockers.append(f"P&L von {position.pnl_pct:+.1f}% ist plausibilitätskritisch")
        if position.atr_pct is None or position.beta is None:
            limitations.append("ATR oder Beta fehlt")
        if ticker not in fundamentals_by_ticker:
            limitations.append("Fundamental-Snapshot fehlt")
        status = "blocked" if blockers else "limited" if limitations else "trusted"
        details = [*blockers, *limitations]
        result[ticker] = {
            "status": status,
            "detail": "; ".join(details) if details else "Kurs-, Risiko- und Fundamentaldaten sind plausibel.",
        }
    return result


def _position_is_implausible(position: PortfolioPosition) -> bool:
    if position.entry_price <= 0 or position.current_price <= 0:
        return True
    return position.pnl_pct > IMPLAUSIBLE_GAIN_PCT or position.pnl_pct < IMPLAUSIBLE_LOSS_PCT


def _build_issues(
    *,
    open_tickers: list[str],
    missing_price_tickers: list[str],
    stale_price_tickers: list[str],
    missing_yahoo_tickers: list[str],
    missing_fundamentals: list[str],
    missing_risk_metrics: list[str],
    missing_stops: list[str],
    implausible: list[str],
    isin_mappings_count: int,
    freshness: list[Any],
    events: list[DataQualityEvent],
) -> list[DataDiagnosticIssue]:
    issues: list[DataDiagnosticIssue] = []
    if not open_tickers:
        issues.append(DataDiagnosticIssue(
            key="no_open_positions", label="Kein Depot importiert", severity="info",
            detail="Es sind keine offenen Positionen gespeichert.", category="portfolio",
        ))
    if missing_price_tickers:
        issues.append(DataDiagnosticIssue(
            key="missing_price_cache", label="Kursdaten fehlen", severity="critical",
            detail=f"{len(missing_price_tickers)} offene Positionen haben keine Kursdaten.",
            tickers=missing_price_tickers, action_label="Fehlende Kurse laden", job_type="refresh_prices",
            job_payload={"mode": "manual", "range": "1y", "tickers": missing_price_tickers},
            category="price", blocks_decisions=True,
        ))
    if stale_price_tickers:
        issues.append(DataDiagnosticIssue(
            key="stale_price_cache", label="Kursdaten veraltet", severity="warning",
            detail=f"{len(stale_price_tickers)} offene Positionen sind älter als {STALE_POSITION_PRICE_DAYS} Tage.",
            tickers=stale_price_tickers, action_label="Kurse aktualisieren", job_type="refresh_prices",
            job_payload={"mode": "manual", "range": "6m", "tickers": stale_price_tickers}, category="price",
        ))
    if implausible:
        issues.append(DataDiagnosticIssue(
            key="implausible_positions", label="Positionswerte prüfen", severity="critical",
            detail="Extreme P&L-Werte deuten auf Währungs-, Split- oder Ticker-Zuordnungsfehler hin.",
            tickers=implausible, category="portfolio", blocks_decisions=True,
        ))
    if missing_fundamentals:
        issues.append(DataDiagnosticIssue(
            key="missing_fundamentals", label="Fundamentaldaten fehlen", severity="warning",
            detail=f"Für {len(missing_fundamentals)} offene Positionen fehlt ein Fundamental-Snapshot.",
            tickers=missing_fundamentals, action_label="Fundamentaldaten laden", job_type="refresh_fundamentals",
            job_payload={"mode": "manual", "tickers": missing_fundamentals}, category="fundamental",
        ))
    if missing_risk_metrics:
        issues.append(DataDiagnosticIssue(
            key="missing_risk_metrics", label="Risikokennzahlen unvollständig", severity="warning",
            detail="ATR, Beta oder Beta-Balancer fehlen bei einzelnen Positionen.",
            tickers=missing_risk_metrics, category="portfolio",
        ))
    if missing_stops:
        issues.append(DataDiagnosticIssue(
            key="missing_stops", label="Stop-Abdeckung unvollständig", severity="warning",
            detail=f"Für {len(missing_stops)} Positionen ist kein Stop-Kurs gepflegt.",
            tickers=missing_stops, category="portfolio",
        ))
    if missing_yahoo_tickers:
        issues.append(DataDiagnosticIssue(
            key="missing_yahoo_symbol", label="Yahoo-Symbol fehlt", severity="warning",
            detail="Prüfe die Ticker-/ISIN-Zuordnung für diese Positionen.",
            tickers=missing_yahoo_tickers, category="mapping",
        ))
    if isin_mappings_count == 0 and open_tickers:
        issues.append(DataDiagnosticIssue(
            key="no_isin_mappings", label="Keine ISIN-Zuordnungen", severity="info",
            detail="Gespeicherte ISIN-Zuordnungen machen Folgeimporte reproduzierbar.", category="mapping",
        ))
    stale_services = [item for item in freshness if item.status != "fresh"]
    if stale_services:
        issues.append(DataDiagnosticIssue(
            key="stale_services", label="Datenbereiche nicht aktuell", severity="warning",
            detail=", ".join(_freshness_label(item.name) for item in stale_services),
            category="freshness",
        ))
    actionable_events = [event for event in events if event.event_type != "ticker_mapping"]
    if actionable_events:
        issues.append(DataDiagnosticIssue(
            key="corporate_action_candidates", label="Kapitalmaßnahmen prüfen", severity="warning",
            detail=f"{len(actionable_events)} mögliche Split- oder Dividendenereignisse erkannt.",
            tickers=sorted({event.ticker for event in actionable_events}), category="corporate_action",
        ))
    return issues


def _detect_corporate_action_candidates(tickers: list[str]) -> list[DataQualityEvent]:
    events: list[DataQualityEvent] = []
    start = date.today() - timedelta(days=150)
    for ticker in tickers:
        try:
            bars = price_repository.list_price_bars(ticker, start_date=start)
        except PriceRepositoryUnavailable:
            continue
        ticker_events: list[DataQualityEvent] = []
        for previous, current in zip(bars, bars[1:]):
            if not previous.close or not current.close or previous.close <= 0:
                continue
            raw_return = current.close / previous.close - 1
            adjusted_return = raw_return
            if previous.adj_close and current.adj_close and previous.adj_close > 0:
                adjusted_return = current.adj_close / previous.adj_close - 1
            divergence = adjusted_return - raw_return
            if abs(raw_return) >= 0.35 and abs(adjusted_return) <= 0.15:
                ticker_events.append(DataQualityEvent(
                    ticker=ticker,
                    event_type="split_candidate",
                    event_date=current.date.isoformat(),
                    label="Möglicher Aktiensplit",
                    detail=f"Rohkurs {raw_return * 100:+.1f}%, adjustiert {adjusted_return * 100:+.1f}%.",
                    severity="critical",
                ))
            elif raw_return < -0.015 and divergence >= 0.02 and abs(adjusted_return) <= 0.12:
                ticker_events.append(DataQualityEvent(
                    ticker=ticker,
                    event_type="dividend_candidate",
                    event_date=current.date.isoformat(),
                    label="Mögliche Ausschüttung",
                    detail=f"Differenz zwischen Roh- und adjustierter Rendite {divergence * 100:.1f}%.",
                    severity="info",
                ))
        if ticker_events:
            events.append(ticker_events[-1])
    return events[:25]


def _freshness_label(name: str) -> str:
    return {
        "prices": "Kurse",
        "market_snapshot": "Marktstatus",
        "trend_benchmark": "Trend-Benchmark",
        "market_breadth": "Marktbreite",
        "relative_strength": "Relative Stärke",
        "fundamentals_tracked": "Fundamentaldaten",
        "institutional_13f": "13F",
        "sell_ranking": "Verkaufsranking",
    }.get(name, name)


def _summary(status: str, positions: int, critical: int, warnings: int) -> str:
    if positions == 0:
        return "Noch kein Depot importiert; allgemeine Datenaktualität wurde geprüft."
    if status == "blocked":
        return f"{critical} kritische Datenprobleme blockieren verlässliche Entscheidungen."
    if status == "limited":
        return f"Datenbasis eingeschränkt: {warnings} Hinweise sollten geprüft werden."
    return "Datenbasis aktuell und plausibel. Entscheidungen können auf den gespeicherten Daten aufbauen."
