from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.data_sources.finra_margin import FinraMarginDebtUnavailable, fetch_latest_margin_debt_snapshot
from app.domain.market.ampel import (
    GREEN_CONFIRMATION_DAYS,
    UPTREND_CONFIRMATION_DAYS,
    TrendAmpelBar,
    TrendAmpelPoint,
    compute_trend_ampel,
)
from app.domain.market.constants import (
    DEFAULT_MARKET_UNIVERSE_KEY,
    DEFAULT_MARKET_UNIVERSE_TICKERS,
    MARKET_INDEX_FALLBACK_TICKERS,
    SECTOR_ETFS,
    SECTOR_ETF_TICKERS,
)
from app.domain.market.regime import STRESS_VOLATILITY_REGIMES, MarketRegimeInput, classify_market_regime
from app.domain.market.volatility import (
    VOLATILITY_TICKERS,
    compute_volatility_dashboard,
    summarize_volatility_points,
)
from app.repositories import market as market_repository
from app.repositories.market import (
    BreadthDailyWrite,
    MarketOhlcvPoint,
    MarketPricePoint,
    MarketRepositoryUnavailable,
    MarketSnapshotWrite,
)
from app.schemas import (
    BreadthPoint,
    BreadthResponse,
    KpiCard,
    MarketAmpelChangeCard,
    MarketAmpelChartMarker,
    MarketAmpelChartPoint,
    MarketAmpelCycle,
    MarketAmpelDistanceTile,
    MarketAmpelHero,
    MarketAmpelLight,
    MarketAmpelPhaseInfo,
    MarketAmpelResponse,
    MarketAmpelWarningCheck,
    MarketDeepAnalysisCheck,
    MarketDeepAnalysisMetric,
    MarketDeepAnalysisPoint,
    MarketDeepAnalysisResponse,
    MarketDiagnosticCheck,
    MarketDiagnosticsResponse,
    MarketIntermarketItem,
    MarketOverviewResponse,
    MarketSectorRotationGroup,
    MarketSectorRotationItem,
    MarketTrendAmpel,
    SectorRankingPoint,
    SectorRankingResponse,
    SectorRankingRow,
    VolatilityPoint,
    VolatilityResponse,
    VolatilityStatusCard,
)


MARKET_TREND_BENCHMARK = "^GSPC"
MARKET_AMPEL_INDEXES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^RUT": "Russell 2000",
}
INTERMARKET_INDEXES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq Composite",
    "^RUT": "Russell 2000",
}
DEFENSIVE_SECTOR_TICKERS = ("XLU", "XLP")
OFFENSIVE_SECTOR_TICKERS = ("XLK", "XLY")


@dataclass(frozen=True)
class BreadthComputationPoint:
    universe: str
    date: date
    advancers: int
    decliners: int
    ad_line: float
    mcclellan: float
    pct_above_20sma: float | None
    pct_above_50sma: float | None
    pct_above_200sma: float | None
    new_highs: int
    new_lows: int
    coverage_ratio: float
    universe_size: int
    loaded_universe: int
    covered_count: int
    valid_for_50sma: int
    valid_for_200sma: int


def get_market_overview() -> MarketOverviewResponse:
    try:
        snapshot = market_repository.get_latest_market_snapshot()
    except MarketRepositoryUnavailable:
        snapshot = None

    if snapshot is None:
        return _missing_market_overview()

    metrics = snapshot.metrics_json or {}
    trend_ampel = _trend_ampel_from_metrics(metrics)
    return MarketOverviewResponse(
        as_of=snapshot.date.isoformat(),
        source="database",
        data_status=_data_status_for_date(snapshot.date),
        message=_market_snapshot_message(snapshot.date, metrics),
        phase=_normalize_phase(snapshot.ampel_phase),
        phase_label=_phase_label(snapshot.ampel_phase),
        action=str(metrics.get("action") or _action_for_phase(snapshot.ampel_phase)),
        warning_count=snapshot.warning_count,
        breadth_mode=_normalize_breadth_mode(snapshot.breadth_mode),
        volatility_regime=snapshot.volatility_regime or "Nicht berechnet",
        trend_ampel=trend_ampel,
        kpis=_kpis_from_metrics(metrics),
    )


def get_market_ampel(
    *,
    ticker: str = MARKET_TREND_BENCHMARK,
    days: int = 90,
) -> MarketAmpelResponse:
    clean_ticker = _normalize_ampel_ticker(ticker)
    clean_days = max(30, min(240, int(days)))
    start_date = date.today() - timedelta(days=max(320, clean_days + 280))
    bars, used_ticker = _load_cached_index_ohlcv(clean_ticker, start_date=start_date)

    if len(bars) < 2:
        return _missing_market_ampel(clean_ticker)

    points = compute_trend_ampel([_trend_bar_from_ohlcv(point) for point in bars])
    if not points:
        return _missing_market_ampel(clean_ticker)

    overview = get_market_overview()
    volatility = get_volatility()
    intermarket = _cached_intermarket_divergence()
    rotation_groups, defensive_lead, defensive_spread = _cached_sector_rotation()
    return build_market_ampel_response(
        ticker=clean_ticker,
        name=MARKET_AMPEL_INDEXES.get(clean_ticker, clean_ticker),
        points=points,
        days=clean_days,
        price_ticker=used_ticker,
        overview=overview,
        volatility=volatility,
        intermarket=intermarket,
        rotation_groups=rotation_groups,
        defensive_lead=defensive_lead,
        defensive_spread_pct=defensive_spread,
    )


def build_market_ampel_response(
    *,
    ticker: str,
    name: str,
    points: Sequence[TrendAmpelPoint],
    days: int,
    price_ticker: str | None = None,
    overview: MarketOverviewResponse,
    volatility: VolatilityResponse,
    intermarket: list[MarketIntermarketItem],
    rotation_groups: list[MarketSectorRotationGroup],
    defensive_lead: bool | None,
    defensive_spread_pct: float | None,
) -> MarketAmpelResponse:
    latest = points[-1]
    previous = points[-2] if len(points) >= 2 else None
    anchor_date, floor_mark, startschuss_low = _last_cycle_markers(points, latest)
    vix_regime = _volatility_card_status(volatility, "VIX Regime")
    warning_checks = _build_ampel_warning_checks(
        points=points,
        latest=latest,
        intermarket=intermarket,
        defensive_lead=defensive_lead,
        defensive_spread_pct=defensive_spread_pct,
        index_name=name,
    )
    warning_count = sum(1 for item in warning_checks if item.active_warning)
    mode, hero_tone, action = _legacy_market_action_and_tone(
        latest.phase,
        warning_count,
        overview.breadth_mode,
        vix_regime,
    )
    phase_info = _ampel_phase_info(
        latest,
        anchor_date=anchor_date,
        floor_mark=floor_mark,
        startschuss_low=startschuss_low,
    )
    chart_points = _ampel_chart_points(points[-days:])
    return MarketAmpelResponse(
        as_of=latest.date,
        ticker=ticker,
        name=name,
        source="database",
        data_status=_ampel_data_status(date.fromisoformat(latest.date), ticker=ticker, price_ticker=price_ticker),
        message=_ampel_data_message(ticker=ticker, price_ticker=price_ticker),
        warning_count=warning_count,
        breadth_mode=overview.breadth_mode,
        volatility_regime=volatility.regime,
        vix_regime=vix_regime,
        hero=MarketAmpelHero(
            mode=mode,
            tone=hero_tone,
            action=action,
            reasons=_ampel_reasons(
                latest,
                warning_count=warning_count,
                breadth_mode=overview.breadth_mode,
                vix_regime=vix_regime,
                anchor_date=anchor_date,
                floor_mark=floor_mark,
                startschuss_low=startschuss_low,
            ),
        ),
        phase_info=phase_info,
        lights=_ampel_lights(latest.phase),
        cycle=_ampel_cycle(
            latest,
            anchor_date=anchor_date,
            floor_mark=floor_mark,
            startschuss_low=startschuss_low,
        ),
        change_cards=_ampel_change_cards(
            latest=latest,
            previous=previous,
            warning_count=warning_count,
            breadth_mode=overview.breadth_mode,
            volatility=volatility,
            index_name=name,
        ),
        distance_tiles=_ampel_distance_tiles(latest, index_name=name),
        warning_checks=warning_checks,
        chart_points=chart_points,
        chart_markers=_ampel_chart_markers(chart_points, latest, anchor_date=anchor_date, floor_mark=floor_mark),
    )


def get_breadth(universe: str = DEFAULT_MARKET_UNIVERSE_KEY, *, limit: int = 160) -> BreadthResponse:
    try:
        rows = market_repository.list_breadth_daily(universe=universe, limit=limit)
    except MarketRepositoryUnavailable:
        rows = []

    if not rows:
        return _missing_breadth(universe)

    points = [
        BreadthPoint(
            date=row.date.isoformat(),
            advancers=row.advancers,
            decliners=row.decliners,
            ad_line=float(row.ad_line or 0),
            mcclellan=float(row.mcclellan or 0),
            pct_above_50sma=float(row.pct_above_50sma or 0),
            pct_above_200sma=float(row.pct_above_200sma or 0),
            new_highs=int(row.new_highs or 0),
            new_lows=int(row.new_lows or 0),
        )
        for row in rows
    ]
    latest_meta = _breadth_metadata_with_legacy_fallback(rows)
    requested_universe = _metadata_int(latest_meta, "universe_size", "requested_universe")
    loaded_universe = _metadata_int(latest_meta, "loaded_universe", "covered_count")
    return BreadthResponse(
        as_of=points[-1].date,
        universe=universe,
        source="database",
        data_status=_data_status_for_date(rows[-1].date),
        message=_breadth_message(rows[-1].date, latest_meta),
        coverage_ratio=float(latest_meta.get("coverage_ratio") or 0),
        loaded_universe=loaded_universe,
        requested_universe=requested_universe or None,
        daily_covered_count=_metadata_int(latest_meta, "daily_covered_count", "covered_count"),
        valid_for_50sma=_metadata_int(latest_meta, "valid_for_50sma"),
        valid_for_200sma=_metadata_int(latest_meta, "valid_for_200sma"),
        nhnl_uses_intraday=bool(latest_meta.get("nhnl_uses_intraday")),
        points=points,
    )


def get_market_deep_analysis(
    universe: str = DEFAULT_MARKET_UNIVERSE_KEY,
    *,
    limit: int = 260,
) -> MarketDeepAnalysisResponse:
    clean_limit = max(60, min(500, int(limit)))
    try:
        rows = market_repository.list_breadth_daily(universe=universe, limit=clean_limit)
    except MarketRepositoryUnavailable:
        rows = []

    if len(rows) <= 20:
        return _missing_market_deep_analysis(universe)

    points = _deep_analysis_points(rows)
    valid_points = [point for point in points if point.mcclellan is not None or point.pct_above_50sma is not None]
    if not valid_points:
        return _missing_market_deep_analysis(universe)

    latest = valid_points[-1]
    latest_row = rows[-1]
    latest_meta = _breadth_metadata_with_legacy_fallback(rows)
    requested_universe_raw = _metadata_int(latest_meta, "universe_size", "requested_universe")
    requested_universe = requested_universe_raw or None
    loaded_universe = _metadata_int(latest_meta, "loaded_universe", "covered_count")
    daily_covered_count = _metadata_int(latest_meta, "daily_covered_count", "covered_count")
    valid_for_50sma = _metadata_int(latest_meta, "valid_for_50sma")
    valid_for_200sma = _metadata_int(latest_meta, "valid_for_200sma")
    nhnl_uses_intraday = bool(latest_meta.get("nhnl_uses_intraday"))
    coverage_ratio = float(latest_meta.get("coverage_ratio") or 0)
    min_required = max(350, int((requested_universe or 0) * 0.18))
    if requested_universe and loaded_universe < min_required:
        return _missing_market_deep_analysis(
            universe,
            message=(
                "Tiefenanalyse ist unvollständig. Das gespeicherte Universe enthält nur "
                f"{loaded_universe}/{requested_universe} auswertbare Titel; benötigt werden mindestens {min_required}. "
                "Starte auf der Jobs-Seite 'Alles initialisieren'."
            ),
            coverage_ratio=coverage_ratio,
            loaded_universe=loaded_universe,
            requested_universe=requested_universe,
            daily_covered_count=daily_covered_count,
            valid_for_50sma=valid_for_50sma,
            valid_for_200sma=valid_for_200sma,
            nhnl_uses_intraday=nhnl_uses_intraday,
        )
    spx_at_high, ad_at_high, index_ad_detail = _index_ad_confirmation(points)
    p50_divergence = bool(spx_at_high and latest.pct_above_50sma is not None and latest.pct_above_50sma < 70)
    recent_thrust = any((point.deemer_ratio or 0) > 1.97 for point in valid_points[-20:])

    metrics = [
        MarketDeepAnalysisMetric(
            label="McClellan Osc.",
            value=_format_number(latest.mcclellan, digits=1),
            detail=_mcclellan_label(latest.mcclellan),
            tone=_tone_for_mcclellan(latest.mcclellan),
        ),
        MarketDeepAnalysisMetric(
            label="NH/NL Ratio",
            value=_format_number(latest.nh_nl_ratio, digits=2) if latest.nh_nl_ratio is not None else f"{latest.new_highs}/{latest.new_lows}",
            detail=f"{latest.new_highs} Hochs / {latest.new_lows} Tiefs",
            tone=_tone_for_ratio(latest.nh_nl_ratio, good=1.0, warning=0.5),
        ),
        MarketDeepAnalysisMetric(
            label="% > 50-SMA",
            value=_format_optional_pct(latest.pct_above_50sma),
            detail="Überhitzt >70%, schwach <30%",
            tone=_tone_for_deep_pct(latest.pct_above_50sma, good=70, warning=30),
        ),
        MarketDeepAnalysisMetric(
            label="% > 200-SMA",
            value=_format_optional_pct(latest.pct_above_200sma),
            detail="Langfristige Marktteilnahme",
            tone=_tone_for_deep_pct(latest.pct_above_200sma, good=55, warning=40),
        ),
        MarketDeepAnalysisMetric(
            label="Deemer Ratio",
            value=_format_number(latest.deemer_ratio, digits=2),
            detail=_deemer_label(latest.deemer_ratio),
            tone=_tone_for_deemer(latest.deemer_ratio),
        ),
    ]
    checks = [
        MarketDeepAnalysisCheck(
            label="Keine Divergenz Index vs. A/D-Linie",
            passed=not (spx_at_high and not ad_at_high),
            detail=index_ad_detail,
            tone="good" if not (spx_at_high and not ad_at_high) else "warning",
        ),
        MarketDeepAnalysisCheck(
            label="Keine % > 50-SMA Divergenz",
            passed=not p50_divergence,
            detail=(
                f"Divergenz: {latest.pct_above_50sma:.0f}% < 70%"
                if p50_divergence and latest.pct_above_50sma is not None
                else f"{latest.pct_above_50sma:.0f}% >= 70% - OK"
                if latest.pct_above_50sma is not None
                else "n/a"
            ),
            tone="good" if not p50_divergence else "warning",
        ),
        MarketDeepAnalysisCheck(
            label="McClellan > 0",
            passed=bool(latest.mcclellan is not None and latest.mcclellan > 0),
            detail=f"McClellan: {_format_number(latest.mcclellan, digits=1)}",
            tone="good" if latest.mcclellan is not None and latest.mcclellan > 0 else "warning",
        ),
        MarketDeepAnalysisCheck(
            label="% über 50-SMA > 70%",
            passed=bool(latest.pct_above_50sma is not None and latest.pct_above_50sma > 70),
            detail=_format_optional_pct(latest.pct_above_50sma),
            tone="good" if latest.pct_above_50sma is not None and latest.pct_above_50sma > 70 else "warning",
        ),
        MarketDeepAnalysisCheck(
            label="NH/NL Ratio > 1",
            passed=bool(latest.nh_nl_ratio is not None and latest.nh_nl_ratio > 1),
            detail=f"Ratio: {_format_number(latest.nh_nl_ratio, digits=1)}",
            tone="good" if latest.nh_nl_ratio is not None and latest.nh_nl_ratio > 1 else "warning",
        ),
        MarketDeepAnalysisCheck(
            label="Deemer Ratio >= 1.97 (Breakaway)",
            passed=bool(latest.deemer_ratio is not None and latest.deemer_ratio >= 1.97),
            detail=f"Ratio: {_format_number(latest.deemer_ratio, digits=2)} · {_deemer_label(latest.deemer_ratio)}",
            tone="good" if latest.deemer_ratio is not None and latest.deemer_ratio >= 1.97 else "warning",
        ),
    ]
    if recent_thrust:
        checks.append(
            MarketDeepAnalysisCheck(
                label="Breitenschub in den letzten 20 Tagen",
                passed=True,
                detail="Deemer Ratio > 1.97 erkannt.",
                tone="good",
            )
        )

    nhnl_note = "NH/NL auf Tageshoch/-tief" if nhnl_uses_intraday else "NH/NL fallback auf Schlusskurs"
    message = (
        "Tiefenanalyse aus gespeicherten Breadth-Daten; "
        f"{nhnl_note}; Deemer nutzt aktuell Advancer/Decliner als Volumen-Proxy."
    )
    if requested_universe and loaded_universe and loaded_universe < requested_universe * 0.8:
        message = (
            f"Universe-Abdeckung unter 80% ({loaded_universe}/{requested_universe}). "
            "Tiefenanalyse läuft mit den verfügbaren gespeicherten Kursdaten."
        )

    return MarketDeepAnalysisResponse(
        as_of=latest.date,
        source="database",
        data_status=_data_status_for_date(latest_row.date),
        message=message,
        universe=universe,
        coverage_ratio=coverage_ratio,
        loaded_universe=loaded_universe,
        requested_universe=requested_universe,
        daily_covered_count=daily_covered_count,
        valid_for_50sma=valid_for_50sma,
        valid_for_200sma=valid_for_200sma,
        nhnl_uses_intraday=nhnl_uses_intraday,
        metrics=metrics,
        checks=checks,
        points=points[-clean_limit:],
    )


def _missing_market_overview() -> MarketOverviewResponse:
    return MarketOverviewResponse(
        as_of=date.today().isoformat(),
        source="missing",
        data_status="missing",
        message="Keine Market-Snapshots im Cache. Starte Marktdaten, Market Breadth und RS Ratings über die Jobs-Seite.",
        phase="neutral",
        phase_label="Nicht berechnet",
        action="Marktdaten initial laden, bevor Marktampel und Risikoanalyse bewertet werden.",
        warning_count=0,
        breadth_mode="wachsam",
        volatility_regime="Nicht berechnet",
        trend_ampel=None,
        kpis=[
            KpiCard(label="S&P 500", value="-", detail="Price Cache fehlt", tone="neutral"),
            KpiCard(label="Nasdaq", value="-", detail="Price Cache fehlt", tone="neutral"),
            KpiCard(label="Breadth", value="-", detail="Breadth-Job fehlt", tone="warning"),
            KpiCard(label="Volatilität", value="-", detail="Volatilitätsdaten fehlen", tone="warning"),
        ],
    )


def _missing_breadth(universe: str) -> BreadthResponse:
    return BreadthResponse(
        as_of=date.today().isoformat(),
        universe=universe,
        source="missing",
        data_status="missing",
        message="Keine Breadth-Werte im Cache. Starte zuerst refresh_prices und danach refresh_breadth.",
        coverage_ratio=0.0,
        points=[],
    )


def _missing_market_deep_analysis(
    universe: str,
    *,
    message: str = "Keine ausreichenden Breadth-Daten im Cache. Starte refresh_prices und danach refresh_breadth.",
    coverage_ratio: float = 0.0,
    loaded_universe: int = 0,
    requested_universe: int | None = None,
    daily_covered_count: int = 0,
    valid_for_50sma: int = 0,
    valid_for_200sma: int = 0,
    nhnl_uses_intraday: bool = False,
) -> MarketDeepAnalysisResponse:
    return MarketDeepAnalysisResponse(
        as_of=date.today().isoformat(),
        source="missing",
        data_status="missing",
        message=message,
        universe=universe,
        coverage_ratio=coverage_ratio,
        loaded_universe=loaded_universe,
        requested_universe=requested_universe,
        daily_covered_count=daily_covered_count,
        valid_for_50sma=valid_for_50sma,
        valid_for_200sma=valid_for_200sma,
        nhnl_uses_intraday=nhnl_uses_intraday,
        metrics=[],
        checks=[],
        points=[],
    )


def get_volatility(*, limit: int = 180) -> VolatilityResponse:
    try:
        points = _cached_volatility_points(limit=limit)
    except MarketRepositoryUnavailable:
        points = []
    summary = summarize_volatility_points(points)
    source = "database" if points else "missing"
    return VolatilityResponse(
        as_of=points[-1].date if points else date.today().isoformat(),
        source=source,
        regime=str(summary.get("regime") or "Nicht berechnet"),
        status_cards=[VolatilityStatusCard.model_validate(item) for item in summary.get("status_cards", [])],
        points=[VolatilityPoint.model_validate(asdict(point)) for point in points],
    )


def get_sector_ranking(*, mode: str = "daily", periods: int = 15) -> SectorRankingResponse:
    clean_mode = "weekly" if mode == "weekly" else "daily"
    lookback_days = 210 if clean_mode == "weekly" else 90
    start_date = date.today() - timedelta(days=lookback_days)
    try:
        series = market_repository.load_cached_prices(SECTOR_ETF_TICKERS, start_date=start_date)
    except MarketRepositoryUnavailable:
        series = {}

    rows, history = compute_sector_ranking(
        series,
        mode=clean_mode,
        periods=periods,
    )
    if not rows:
        return SectorRankingResponse(
            as_of=date.today().isoformat(),
            source="missing",
            data_status="missing",
            mode=clean_mode,
            message="Keine Sektor-ETF-Preise im Cache. Starte refresh_prices mit Preset sector oder all.",
            rows=[],
            top=[],
            bottom=[],
            history=[],
        )

    as_of = max(point.date for points in series.values() for point in points).isoformat()
    status = _data_status_for_date(date.fromisoformat(as_of))
    return SectorRankingResponse(
        as_of=as_of,
        source="database",
        data_status=status,
        mode=clean_mode,
        message=f"Sektor-Ranking aus gecachten SPDR-Sektor-ETFs; Modus {clean_mode}.",
        rows=rows,
        top=rows[:3],
        bottom=list(reversed(rows[-3:])),
        history=history,
    )


def get_market_diagnostics() -> MarketDiagnosticsResponse:
    overview = get_market_overview()
    breadth = get_breadth()
    volatility = get_volatility()
    intermarket = _cached_intermarket_divergence()
    rotation_groups, defensive_lead, defensive_spread = _cached_sector_rotation()
    benchmark_drawdown_pct = _cached_benchmark_drawdown_pct()

    checklist = _build_market_diagnostic_checks(
        overview=overview,
        breadth=breadth,
        volatility=volatility,
        intermarket=intermarket,
        defensive_lead=defensive_lead,
        defensive_spread_pct=defensive_spread,
        benchmark_drawdown_pct=benchmark_drawdown_pct,
    )
    warning_count = sum(1 for item in checklist if not item.passed and item.tone in {"warning", "bad"})
    source = _diagnostics_source(overview, intermarket, rotation_groups)
    data_status = overview.data_status if source != "missing" else "missing"

    return MarketDiagnosticsResponse(
        as_of=overview.as_of,
        source=source,
        data_status=data_status,
        message=_market_diagnostics_message(source, overview, breadth, intermarket, rotation_groups),
        summary=_market_diagnostics_summary(warning_count, defensive_lead, intermarket),
        warning_count=warning_count,
        defensive_lead=defensive_lead,
        defensive_spread_pct=defensive_spread,
        checklist=checklist,
        intermarket=intermarket,
        sector_rotation=rotation_groups,
    )


def refresh_market_breadth(
    *,
    tickers: list[str] | None = None,
    universe: str = DEFAULT_MARKET_UNIVERSE_KEY,
    lookback_days: int = 370,
) -> dict:
    clean_tickers = _normalize_tickers(tickers or DEFAULT_MARKET_UNIVERSE_TICKERS)
    start_date = date.today() - timedelta(days=max(90, min(2000, lookback_days)))
    series = market_repository.load_cached_ohlcv_for_tickers(clean_tickers, start_date=start_date)
    computed = compute_breadth_series(series, universe=universe, universe_size=len(clean_tickers))
    if not computed:
        return {
            "ok": False,
            "skipped": True,
            "reason": "Keine ausreichenden Price-Bars im Cache. Zuerst refresh_prices ausführen.",
            "universe": universe,
            "universe_size": len(clean_tickers),
            "covered_tickers": len(series),
        }

    writes = [
        BreadthDailyWrite(
            universe=point.universe,
            date=point.date,
            advancers=point.advancers,
            decliners=point.decliners,
            ad_line=point.ad_line,
            mcclellan=point.mcclellan,
            pct_above_20sma=point.pct_above_20sma,
            pct_above_50sma=point.pct_above_50sma,
            pct_above_200sma=point.pct_above_200sma,
            new_highs=point.new_highs,
            new_lows=point.new_lows,
            metadata_json={
                "coverage_ratio": point.coverage_ratio,
                "universe_size": point.universe_size,
                "loaded_universe": point.loaded_universe,
                "covered_count": point.covered_count,
                "daily_covered_count": point.covered_count,
                "valid_for_50sma": point.valid_for_50sma,
                "valid_for_200sma": point.valid_for_200sma,
                "nhnl_uses_intraday": True,
            },
        )
        for point in computed
    ]
    rows_written = market_repository.upsert_breadth_daily(writes)
    volatility_points = _cached_volatility_points(limit=180)
    volatility_summary = summarize_volatility_points(volatility_points)
    margin_debt_summary = _latest_margin_debt_summary()
    trend_point = _latest_cached_trend_ampel_point(MARKET_TREND_BENCHMARK, lookback_days=lookback_days)
    snapshot = build_market_snapshot(
        computed[-1],
        volatility_summary=volatility_summary,
        margin_debt_summary=margin_debt_summary,
        trend_point=trend_point,
        trend_ticker=MARKET_TREND_BENCHMARK,
    )
    market_repository.upsert_market_snapshot(snapshot)
    return {
        "ok": True,
        "universe": universe,
        "universe_size": len(clean_tickers),
        "covered_tickers": len(series),
        "loaded_universe": len(series),
        "records_seen": sum(len(points) for points in series.values()),
        "records_written": rows_written + 1,
        "breadth_rows_written": rows_written,
        "snapshot_date": computed[-1].date.isoformat(),
        "coverage_ratio": computed[-1].coverage_ratio,
        "phase": snapshot.ampel_phase,
        "trend_phase": trend_point.phase if trend_point else None,
        "volatility_regime": snapshot.volatility_regime,
        "margin_debt": margin_debt_summary,
    }


def compute_breadth_series(
    series: Mapping[str, list[MarketPricePoint | MarketOhlcvPoint]],
    *,
    universe: str,
    universe_size: int | None = None,
) -> list[BreadthComputationPoint]:
    clean_series = {
        ticker: sorted(points, key=lambda point: point.date)
        for ticker, points in series.items()
        if len(points) >= 2
    }
    loaded_universe = len(clean_series)
    total_universe_size = universe_size or loaded_universe
    if not clean_series or total_universe_size <= 0:
        return []

    histories: dict[str, list[MarketPricePoint | MarketOhlcvPoint]] = {ticker: [] for ticker in clean_series}
    by_date: dict[date, dict[str, MarketPricePoint | MarketOhlcvPoint]] = {}
    for ticker, points in clean_series.items():
        for point in points:
            by_date.setdefault(point.date, {})[ticker] = point

    ad_line = 0.0
    ema_19: float | None = None
    ema_39: float | None = None
    computed: list[BreadthComputationPoint] = []
    dates = sorted(by_date)
    nh_window = min(252, len(dates) - 2) if len(dates) > 22 else 20

    for current_date in dates:
        todays_points = by_date[current_date]
        advancers = 0
        decliners = 0
        above_20 = 0
        above_50 = 0
        above_200 = 0
        eligible_20 = 0
        eligible_50 = 0
        eligible_200 = 0
        new_highs = 0
        new_lows = 0

        for ticker, point in todays_points.items():
            history = histories[ticker]
            if history:
                previous_close = history[-1].close
                if point.close > previous_close:
                    advancers += 1
                elif point.close < previous_close:
                    decliners += 1

            closes_with_current = [item.close for item in history] + [point.close]
            if len(closes_with_current) >= 20:
                eligible_20 += 1
                above_20 += int(point.close > _mean(closes_with_current[-20:]))
            if len(closes_with_current) >= 50:
                eligible_50 += 1
                above_50 += int(point.close > _mean(closes_with_current[-50:]))
            if len(closes_with_current) >= 200:
                eligible_200 += 1
                above_200 += int(point.close > _mean(closes_with_current[-200:]))

            previous_highs = [_point_high(item) for item in history]
            previous_lows = [_point_low(item) for item in history]
            if len(previous_highs) >= 20:
                new_highs += int(_point_high(point) > max(previous_highs[-nh_window:]))
            if len(previous_lows) >= 20:
                new_lows += int(_point_low(point) < min(previous_lows[-nh_window:]))
            history.append(point)

        net_advances = advancers - decliners
        ad_line += net_advances
        breadth_base = advancers + decliners
        if breadth_base > 0:
            rana = (net_advances / breadth_base) * 1000.0
            ema_19 = _ema(rana, previous=ema_19, period=19)
            ema_39 = _ema(rana, previous=ema_39, period=39)
        mcclellan = (ema_19 - ema_39) if ema_19 is not None and ema_39 is not None else 0.0
        covered_count = len(todays_points)

        computed.append(
            BreadthComputationPoint(
                universe=universe,
                date=current_date,
                advancers=advancers,
                decliners=decliners,
                ad_line=ad_line,
                mcclellan=mcclellan,
                pct_above_20sma=_pct(above_20, eligible_20),
                pct_above_50sma=_pct(above_50, eligible_50),
                pct_above_200sma=_pct(above_200, eligible_200),
                new_highs=new_highs,
                new_lows=new_lows,
                coverage_ratio=loaded_universe / total_universe_size,
                universe_size=total_universe_size,
                loaded_universe=loaded_universe,
                covered_count=covered_count,
                valid_for_50sma=eligible_50,
                valid_for_200sma=eligible_200,
            )
        )

    return computed


def compute_sector_ranking(
    series: Mapping[str, list[MarketPricePoint]],
    *,
    mode: str = "daily",
    periods: int = 15,
) -> tuple[list[SectorRankingRow], list[SectorRankingPoint]]:
    close_by_ticker = {
        ticker: {point.date: point.close for point in sorted(points, key=lambda item: item.date)}
        for ticker, points in series.items()
        if ticker in SECTOR_ETFS and len(points) >= 2
    }
    if not close_by_ticker:
        return [], []

    all_dates = sorted({item_date for closes in close_by_ticker.values() for item_date in closes})
    if len(all_dates) < 2:
        return [], []

    aligned: dict[str, list[float | None]] = {}
    for ticker, closes in close_by_ticker.items():
        previous: float | None = None
        values: list[float | None] = []
        for current_date in all_dates:
            if current_date in closes:
                previous = closes[current_date]
            values.append(previous)
        if sum(value is not None for value in values) >= 2:
            aligned[ticker] = values

    period_returns: list[tuple[date, dict[str, float]]] = []
    step = 5 if mode == "weekly" else 1
    for index in range(step, len(all_dates)):
        current_returns: dict[str, float] = {}
        for ticker, values in aligned.items():
            current = values[index]
            previous = values[index - step]
            if current is None or previous is None or previous <= 0:
                continue
            current_returns[ticker] = (current / previous - 1) * 100
        if current_returns:
            period_returns.append((all_dates[index], current_returns))

    if not period_returns:
        return [], []

    latest_date, latest_returns = period_returns[-1]
    rows = [
        SectorRankingRow(
            ticker=ticker,
            name=SECTOR_ETFS[ticker],
            rank=rank,
            return_pct=return_pct,
            return_1d_pct=_trailing_return(aligned[ticker], 1),
            return_5d_pct=_trailing_return(aligned[ticker], 5),
            return_20d_pct=_trailing_return(aligned[ticker], 20),
        )
        for rank, (ticker, return_pct) in enumerate(
            sorted(latest_returns.items(), key=lambda item: item[1], reverse=True),
            start=1,
        )
    ]

    history: list[SectorRankingPoint] = []
    for current_date, returns in period_returns[-max(1, min(60, periods)) :]:
        for rank, (ticker, return_pct) in enumerate(
            sorted(returns.items(), key=lambda item: item[1], reverse=True),
            start=1,
        ):
            history.append(
                SectorRankingPoint(
                    date=current_date.isoformat(),
                    ticker=ticker,
                    name=SECTOR_ETFS.get(ticker, ticker),
                    rank=rank,
                    return_pct=return_pct,
                )
            )

    return rows, history


def compute_intermarket_divergence(
    series: Mapping[str, list[MarketOhlcvPoint]],
) -> list[MarketIntermarketItem]:
    results: list[MarketIntermarketItem] = []
    for ticker, name in INTERMARKET_INDEXES.items():
        points = sorted(series.get(ticker, []), key=lambda point: point.date)
        if len(points) < 5:
            continue
        latest = points[-1]
        previous = points[-2]
        day_pct = _safe_pct_change(latest.close, previous.close)
        previous_highs = [point.high for point in points[:-1]][-20:]
        valid_previous_highs = [value for value in previous_highs if value is not None]
        reference_high = max(valid_previous_highs) if len(valid_previous_highs) >= 10 else None
        dist_to_high = _safe_pct_change(latest.close, reference_high)
        at_20d_high = bool(reference_high and latest.close >= reference_high * 0.998)
        tone = _tone_for_intermarket(at_20d_high, dist_to_high)
        results.append(
            MarketIntermarketItem(
                ticker=ticker,
                name=name,
                close=round(latest.close, 2),
                day_pct=_round_optional(day_pct),
                dist_to_20d_high_pct=_round_optional(dist_to_high),
                at_20d_high=at_20d_high,
                tone=tone,
                status=_intermarket_status(at_20d_high, dist_to_high),
            )
        )
    return results


def compute_sector_rotation(
    series: Mapping[str, list[MarketPricePoint]],
    *,
    lookback_days: int = 10,
) -> tuple[list[MarketSectorRotationGroup], bool | None, float | None]:
    defensive_items = _sector_rotation_items(series, DEFENSIVE_SECTOR_TICKERS, "defensive", lookback_days)
    offensive_items = _sector_rotation_items(series, OFFENSIVE_SECTOR_TICKERS, "offensive", lookback_days)
    defensive_avg = _avg_optional([item.return_10d_pct for item in defensive_items])
    offensive_avg = _avg_optional([item.return_10d_pct for item in offensive_items])
    defensive_lead = None
    spread = None
    if defensive_avg is not None and offensive_avg is not None:
        spread = round(defensive_avg - offensive_avg, 2)
        defensive_lead = defensive_avg > offensive_avg

    return (
        [
            MarketSectorRotationGroup(
                group="defensive",
                label="Defensiv",
                avg_return_10d_pct=_round_optional(defensive_avg),
                items=defensive_items,
            ),
            MarketSectorRotationGroup(
                group="offensive",
                label="Offensiv",
                avg_return_10d_pct=_round_optional(offensive_avg),
                items=offensive_items,
            ),
        ],
        defensive_lead,
        spread,
    )


def build_market_snapshot(
    point: BreadthComputationPoint,
    volatility_summary: dict | None = None,
    *,
    margin_debt_summary: dict | None = None,
    trend_point: TrendAmpelPoint | None = None,
    trend_ticker: str = MARKET_TREND_BENCHMARK,
) -> MarketSnapshotWrite:
    volatility_regime = str((volatility_summary or {}).get("regime") or "Nicht berechnet")
    regime = classify_market_regime(
        MarketRegimeInput(
            pct_above_20sma=point.pct_above_20sma,
            pct_above_50sma=point.pct_above_50sma,
            pct_above_200sma=point.pct_above_200sma,
            mcclellan=point.mcclellan,
            advancers=point.advancers,
            decliners=point.decliners,
            new_highs=point.new_highs,
            new_lows=point.new_lows,
            coverage_ratio=point.coverage_ratio,
            universe_size=point.universe_size,
            covered_count=point.loaded_universe,
            volatility_regime=volatility_regime,
            volatility_summary=volatility_summary or {},
            margin_debt_summary=margin_debt_summary or {},
        )
    )
    trend_ampel = _trend_ampel_metrics(trend_point, ticker=trend_ticker)
    metrics = {
        **regime.metrics,
        "breadth_phase": regime.phase,
        "trend_ampel": trend_ampel,
        "daily_covered_count": point.covered_count,
        "valid_for_50sma": point.valid_for_50sma,
        "valid_for_200sma": point.valid_for_200sma,
    }
    if trend_point is not None:
        metrics["action"] = _combined_market_action(
            trend_phase=trend_point.phase,
            breadth_action=regime.action,
            breadth_mode=regime.breadth_mode,
            volatility_regime=volatility_regime,
        )

    return MarketSnapshotWrite(
        date=point.date,
        ampel_phase=trend_point.phase if trend_point is not None else regime.phase,
        warning_count=regime.warning_count,
        breadth_mode=regime.breadth_mode,
        volatility_regime=volatility_regime,
        metrics_json=metrics,
    )


def _latest_cached_trend_ampel_point(ticker: str, *, lookback_days: int) -> TrendAmpelPoint | None:
    start_date = date.today() - timedelta(days=max(250, min(2000, lookback_days)))
    bars, _used_ticker = _load_cached_index_ohlcv(ticker, start_date=start_date)
    if len(bars) < 2:
        return None
    points = compute_trend_ampel([_trend_bar_from_ohlcv(point) for point in bars])
    return points[-1] if points else None


def _cached_volatility_points(*, limit: int = 180):
    start_date = date.today() - timedelta(days=900)
    series = market_repository.load_cached_prices(VOLATILITY_TICKERS, start_date=start_date)
    return compute_volatility_dashboard(series, limit=limit)


def _latest_margin_debt_summary() -> dict:
    try:
        return asdict(fetch_latest_margin_debt_snapshot())
    except FinraMarginDebtUnavailable:
        return {}


def _cached_intermarket_divergence() -> list[MarketIntermarketItem]:
    start_date = date.today() - timedelta(days=120)
    series: dict[str, list[MarketOhlcvPoint]] = {}
    for ticker in INTERMARKET_INDEXES:
        rows, _used_ticker = _load_cached_index_ohlcv(ticker, start_date=start_date)
        series[ticker] = rows
    return compute_intermarket_divergence(series)


def _cached_sector_rotation() -> tuple[list[MarketSectorRotationGroup], bool | None, float | None]:
    start_date = date.today() - timedelta(days=70)
    tickers = [*DEFENSIVE_SECTOR_TICKERS, *OFFENSIVE_SECTOR_TICKERS]
    try:
        series = market_repository.load_cached_prices(tickers, start_date=start_date)
    except MarketRepositoryUnavailable:
        series = {}
    groups, defensive_lead, defensive_spread = compute_sector_rotation(series, lookback_days=10)
    if not any(item.return_10d_pct is not None for group in groups for item in group.items):
        return [], None, None
    return groups, defensive_lead, defensive_spread


def _cached_benchmark_drawdown_pct() -> float | None:
    bars, _used_ticker = _load_cached_index_ohlcv(
        MARKET_TREND_BENCHMARK,
        start_date=date.today() - timedelta(days=420),
    )
    if not bars:
        return None
    closes = [point.close for point in bars if point.close > 0]
    if not closes:
        return None
    high = max(closes)
    if high <= 0:
        return None
    return (closes[-1] / high - 1) * 100


def _deep_analysis_points(rows: Sequence) -> list[MarketDeepAnalysisPoint]:
    points: list[MarketDeepAnalysisPoint] = []
    advancer_window: list[int] = []
    decliner_window: list[int] = []
    for row in rows:
        advancers = int(row.advancers or 0)
        decliners = int(row.decliners or 0)
        advancer_window.append(advancers)
        decliner_window.append(decliners)
        if len(advancer_window) > 10:
            advancer_window.pop(0)
            decliner_window.pop(0)
        deemer_ratio = None
        if len(advancer_window) >= 10 and sum(decliner_window) > 0:
            deemer_ratio = sum(advancer_window) / sum(decliner_window)
        nh_nl_ratio = _safe_ratio(int(row.new_highs or 0), int(row.new_lows or 0))
        points.append(
            MarketDeepAnalysisPoint(
                date=row.date.isoformat(),
                ad_line=float(row.ad_line) if row.ad_line is not None else None,
                mcclellan=float(row.mcclellan) if row.mcclellan is not None else None,
                new_highs=int(row.new_highs or 0),
                new_lows=int(row.new_lows or 0),
                nh_nl_ratio=nh_nl_ratio,
                pct_above_50sma=float(row.pct_above_50sma) if row.pct_above_50sma is not None else None,
                pct_above_200sma=float(row.pct_above_200sma) if row.pct_above_200sma is not None else None,
                deemer_ratio=deemer_ratio,
            )
        )
    return points


def _index_ad_confirmation(points: Sequence[MarketDeepAnalysisPoint]) -> tuple[bool, bool, str]:
    bars, _used_ticker = _load_cached_index_ohlcv(
        MARKET_TREND_BENCHMARK,
        start_date=date.today() - timedelta(days=120),
    )
    if len(bars) < 21 or len(points) < 21:
        return False, False, "S&P- oder A/D-Historie im Cache zu kurz."

    latest_close = bars[-1].close
    previous_highs = [point.high for point in bars[:-1]][-20:]
    previous_ad_values = [point.ad_line for point in points[:-1] if point.ad_line is not None][-20:]
    latest_ad = points[-1].ad_line
    if latest_ad is None or len(previous_highs) < 10 or len(previous_ad_values) < 10:
        return False, False, "A/D-Linie oder 20T-Referenzhoch nicht verfügbar."

    reference_high = max(previous_highs)
    reference_ad_high = max(previous_ad_values)
    spx_at_high = latest_close >= reference_high * 0.998
    ad_at_high = latest_ad >= reference_ad_high * 0.998
    if spx_at_high and ad_at_high:
        detail = "S&P 500 und A/D-Linie bestätigen sich."
    elif spx_at_high:
        detail = "S&P 500 nahe 20T-Hoch, A/D-Linie bestätigt nicht."
    else:
        detail = "S&P 500 nicht nahe 20T-Hoch; keine aktive Divergenz."
    return spx_at_high, ad_at_high, detail


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator > 0:
        return numerator / denominator
    if numerator > 0:
        return float(numerator)
    return None


def _mcclellan_label(value: float | None) -> str:
    if value is None:
        return "Nicht verfügbar"
    if value > 125:
        return "Extrem aufwärts"
    if value > 80:
        return "Überdehnt aufwärts"
    if value > 50:
        return "Impuls aufwärts"
    if value > 0:
        return "Konstruktiv"
    if value > -50:
        return "Schwach"
    if value > -80:
        return "Impuls abwärts"
    if value > -125:
        return "Überdehnt abwärts"
    return "Extrem abwärts"


def _deemer_label(value: float | None) -> str:
    if value is None:
        return "Nicht verfügbar"
    if value >= 1.97:
        return "Sehr gut - Breakaway Momentum"
    if value >= 1.50:
        return "Gut - konstruktiv"
    if value >= 1.00:
        return "Neutral"
    return "Schlecht - schwache Breite"


def _tone_for_mcclellan(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "good"
    if value > -50:
        return "warning"
    return "bad"


def _tone_for_ratio(value: float | None, *, good: float, warning: float) -> str:
    if value is None:
        return "neutral"
    if value > good:
        return "good"
    if value >= warning:
        return "warning"
    return "bad"


def _tone_for_deep_pct(value: float | None, *, good: float, warning: float) -> str:
    if value is None:
        return "neutral"
    if value >= good:
        return "good"
    if value >= warning:
        return "warning"
    return "bad"


def _tone_for_deemer(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value >= 1.50:
        return "good"
    if value >= 1.0:
        return "warning"
    return "bad"


def _build_market_diagnostic_checks(
    *,
    overview: MarketOverviewResponse,
    breadth: BreadthResponse,
    volatility: VolatilityResponse,
    intermarket: list[MarketIntermarketItem],
    defensive_lead: bool | None,
    defensive_spread_pct: float | None,
    benchmark_drawdown_pct: float | None,
) -> list[MarketDiagnosticCheck]:
    trend = overview.trend_ampel
    trend_phase = trend.phase if trend else overview.phase
    stable = trend_phase != "rot" or bool(trend and trend.anchor_date)
    intermarket_divergence = _has_intermarket_divergence(intermarket)
    stress_regime = volatility.regime in STRESS_VOLATILITY_REGIMES
    if not stress_regime:
        stress_regime = any(card.title == "VIX Regime" and card.status == "Stress" for card in volatility.status_cards)

    return [
        _diagnostic_check(
            "data",
            "Price-Cache vorhanden",
            overview.source == "database" or breadth.source == "database",
            "Marktdiagnose nutzt gespeicherte Snapshots und Price-Bars; keine Liveberechnung im Request.",
        ),
        _diagnostic_check(
            "trend",
            "Kein substanzieller Drawdown (> -8%)",
            benchmark_drawdown_pct is None or benchmark_drawdown_pct > -8,
            f"Benchmark-Drawdown: {_format_optional_pct(benchmark_drawdown_pct)}",
        ),
        _diagnostic_check(
            "trend",
            "Stabilisierung?",
            stable,
            f"Phase: {overview.phase_label}"
            + (f" · Ankertag {trend.anchor_date}" if trend and trend.anchor_date else ""),
        ),
        _diagnostic_check(
            "trend",
            "Startschuss (>= Gelb)?",
            trend_phase in {"gelb", "gruen", "aufwaertstrend"},
            f"Trend-Ampel: {_phase_label(trend_phase)}",
        ),
        _diagnostic_check(
            "breadth",
            "Marktbreite?",
            overview.breadth_mode != "schutz",
            f"Modus: {overview.breadth_mode.capitalize()} · Coverage {(breadth.coverage_ratio * 100):.0f}%",
        ),
        _diagnostic_check(
            "volatility",
            "VIX Regime nicht Stress?",
            not stress_regime,
            f"Regime: {volatility.regime}",
        ),
        _diagnostic_check(
            "warning",
            "Warnzeichen <=2?",
            overview.warning_count <= 2,
            f"{overview.warning_count} aktiv",
        ),
        _diagnostic_check(
            "intermarket",
            "Intermarket-Konvergenz",
            not intermarket_divergence,
            _intermarket_detail(intermarket),
        ),
        _diagnostic_check(
            "rotation",
            "Keine Sektorrotation in Defensive",
            defensive_lead is not True,
            "Spread: "
            + (_format_optional_pct(defensive_spread_pct) if defensive_spread_pct is not None else "n/a"),
        ),
    ]


def _diagnostic_check(category: str, label: str, passed: bool, detail: str) -> MarketDiagnosticCheck:
    return MarketDiagnosticCheck(
        category=category,
        label=label,
        passed=passed,
        detail=detail,
        tone="good" if passed else "warning",
    )


def _sector_rotation_items(
    series: Mapping[str, list[MarketPricePoint]],
    tickers: tuple[str, ...],
    group: str,
    lookback_days: int,
) -> list[MarketSectorRotationItem]:
    items: list[MarketSectorRotationItem] = []
    for ticker in tickers:
        points = sorted(series.get(ticker, []), key=lambda point: point.date)
        return_pct = None
        if len(points) > lookback_days:
            return_pct = _safe_pct_change(points[-1].close, points[-1 - lookback_days].close)
        items.append(
            MarketSectorRotationItem(
                ticker=ticker,
                name=SECTOR_ETFS.get(ticker, ticker),
                group=group,
                return_10d_pct=_round_optional(return_pct),
            )
        )
    return items


def _diagnostics_source(
    overview: MarketOverviewResponse,
    intermarket: list[MarketIntermarketItem],
    rotation_groups: list[MarketSectorRotationGroup],
) -> str:
    has_rotation = any(item.return_10d_pct is not None for group in rotation_groups for item in group.items)
    if overview.source == "database" or intermarket or has_rotation:
        return "database"
    if overview.source == "synthetic_fixture":
        return "synthetic_fixture"
    return "missing"


def _market_diagnostics_message(
    source: str,
    overview: MarketOverviewResponse,
    breadth: BreadthResponse,
    intermarket: list[MarketIntermarketItem],
    rotation_groups: list[MarketSectorRotationGroup],
) -> str:
    if source == "missing":
        return "Keine gecachten Marktdaten gefunden. Starte refresh_prices und danach refresh_breadth."
    missing_parts = []
    if overview.source != "database":
        missing_parts.append("MarketSnapshot")
    if breadth.source != "database":
        missing_parts.append("Breadth")
    if not intermarket:
        missing_parts.append("Intermarket-Indizes")
    if not rotation_groups:
        missing_parts.append("Sektor-ETFs")
    if missing_parts:
        return "Teilweise Cache-Abdeckung fehlt: " + ", ".join(missing_parts) + "."
    return "Diagnose aus vorberechneten Snapshots und gecachten Price-Bars."


def _market_diagnostics_summary(
    warning_count: int,
    defensive_lead: bool | None,
    intermarket: list[MarketIntermarketItem],
) -> str:
    if warning_count == 0:
        return "Keine aktiven Markt-Warnzeichen in der täglichen Checkliste."
    if defensive_lead:
        return f"{warning_count} Warnzeichen; defensive Sektoren führen kurzfristig."
    if _has_intermarket_divergence(intermarket):
        return f"{warning_count} Warnzeichen; wichtige Indizes bestätigen Stärke nicht einheitlich."
    if warning_count <= 2:
        return f"{warning_count} Warnzeichen; Umfeld bleibt handelbar, aber selektiv."
    return f"{warning_count} Warnzeichen; Risiko reduzieren und neue Käufe stark filtern."


def _has_intermarket_divergence(items: list[MarketIntermarketItem]) -> bool:
    if len(items) < 2:
        return False
    return any(item.at_20d_high for item in items) and any(not item.at_20d_high for item in items)


def _intermarket_detail(items: list[MarketIntermarketItem]) -> str:
    if not items:
        return "Keine Intermarket-Indexdaten im Cache."
    return " · ".join(
        f"{item.name}: {_format_optional_pct(item.dist_to_20d_high_pct)} zum 20T-Hoch" for item in items
    )


def _tone_for_intermarket(at_20d_high: bool, dist_to_high: float | None) -> str:
    if at_20d_high:
        return "good"
    if dist_to_high is None:
        return "neutral"
    if dist_to_high >= -2:
        return "neutral"
    if dist_to_high >= -5:
        return "warning"
    return "bad"


def _intermarket_status(at_20d_high: bool, dist_to_high: float | None) -> str:
    if at_20d_high:
        return "20T-Hoch bestätigt"
    if dist_to_high is None:
        return "Referenzhoch fehlt"
    if dist_to_high >= -2:
        return "nahe am 20T-Hoch"
    if dist_to_high >= -5:
        return "hinkt hinterher"
    return "deutlich schwächer"


def _safe_pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1) * 100


def _avg_optional(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _format_optional_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def _missing_market_ampel(ticker: str) -> MarketAmpelResponse:
    today = date.today().isoformat()
    return MarketAmpelResponse(
        as_of=today,
        ticker=ticker,
        name=MARKET_AMPEL_INDEXES.get(ticker, ticker),
        source="missing",
        data_status="missing",
        message=(
            f"Keine gecachten OHLCV-Bars für {ticker}. Starte auf der Jobs-Seite refresh_prices "
            "mit Preset all oder market_core."
        ),
        warning_count=0,
        breadth_mode="wachsam",
        volatility_regime="Nicht berechnet",
        vix_regime="n/a",
        hero=MarketAmpelHero(
            mode="Nicht berechnet",
            tone="neutral",
            action="Price-Cache laden, danach Marktampel erneut öffnen.",
            reasons=["Keine Benchmark-Kurse im Cache.", "Die API führt keine Live-yfinance-Ladung im Klickpfad aus."],
        ),
        phase_info=MarketAmpelPhaseInfo(
            phase="neutral",
            label="NEUTRAL",
            reason="Keine ausreichenden Kursdaten für die Trendwende-Ampel.",
            action="Marktdaten laden.",
            tone="neutral",
        ),
        lights=_ampel_lights("neutral"),
        cycle=MarketAmpelCycle(diagnostics=["Keine Kursdaten im Cache"]),
        change_cards=[],
        distance_tiles=[],
        warning_checks=[],
        chart_points=[],
        chart_markers=[],
    )


def _normalize_ampel_ticker(value: str) -> str:
    clean = str(value or "").strip().upper()
    if clean in MARKET_AMPEL_INDEXES:
        return clean
    if clean in {"S&P 500", "SP500", "SPY", "^SPX"}:
        return "^GSPC"
    if clean in {"NASDAQ", "NASDAQ 100", "NASDAQ COMPOSITE", "QQQ", "NDX"}:
        return "^IXIC"
    if clean in {"RUSSELL", "RUSSELL 2000", "IWM"}:
        return "^RUT"
    return MARKET_TREND_BENCHMARK


def _load_cached_index_ohlcv(ticker: str, *, start_date: date) -> tuple[list[MarketOhlcvPoint], str | None]:
    primary_rows: list[MarketOhlcvPoint] = []
    primary_ticker: str | None = None
    for candidate in [ticker, *MARKET_INDEX_FALLBACK_TICKERS.get(ticker, [])]:
        try:
            rows = market_repository.load_cached_ohlcv(candidate, start_date=start_date)
        except MarketRepositoryUnavailable:
            return [], None
        if rows:
            primary_rows = rows
            primary_ticker = candidate
            break
    if not primary_rows:
        return [], None

    if primary_ticker == ticker and _volume_series_unusable(primary_rows):
        for proxy_ticker in MARKET_INDEX_FALLBACK_TICKERS.get(ticker, []):
            try:
                proxy_rows = market_repository.load_cached_ohlcv(proxy_ticker, start_date=start_date)
            except MarketRepositoryUnavailable:
                return primary_rows, primary_ticker
            if proxy_rows and not _volume_series_unusable(proxy_rows):
                return _merge_proxy_volume(primary_rows, proxy_rows), primary_ticker
    return primary_rows, primary_ticker


def _volume_series_unusable(rows: Sequence[MarketOhlcvPoint]) -> bool:
    volumes = [float(point.volume or 0) for point in rows]
    positive = [value for value in volumes if value > 0]
    if len(positive) < min(20, max(1, len(rows) // 4)):
        return True
    return len({round(value) for value in positive[-60:]}) <= 2


def _merge_proxy_volume(
    price_rows: Sequence[MarketOhlcvPoint],
    volume_rows: Sequence[MarketOhlcvPoint],
) -> list[MarketOhlcvPoint]:
    volume_by_date = {point.date: float(point.volume or 0) for point in volume_rows if point.volume and point.volume > 0}
    if not volume_by_date:
        return list(price_rows)
    merged: list[MarketOhlcvPoint] = []
    for point in price_rows:
        merged.append(
            MarketOhlcvPoint(
                ticker=point.ticker,
                date=point.date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=volume_by_date.get(point.date, point.volume),
            )
        )
    return merged


def _ampel_data_message(*, ticker: str, price_ticker: str | None) -> str:
    if price_ticker and price_ticker != ticker:
        return (
            f"Marktampel nutzt vorübergehend {price_ticker} als Proxy, weil {ticker} noch nicht im Cache liegt. "
            "Starte refresh_prices mit Preset market_core/all, um die echten Indexdaten zu laden."
        )
    return "Marktampel aus gecachten Index-OHLCV-Bars. Keine Live-yfinance-Berechnung im Request-Pfad."


def _ampel_data_status(value: date, *, ticker: str, price_ticker: str | None) -> str:
    if price_ticker and price_ticker != ticker:
        return "fallback"
    return _data_status_for_date(value)


def _last_cycle_markers(points: Sequence[TrendAmpelPoint], latest: TrendAmpelPoint) -> tuple[str | None, float | None, float | None]:
    anchor_date = latest.anchor_date or next((point.anchor_date for point in reversed(points) if point.anchor_date), None)
    floor_mark = latest.floor_mark
    if floor_mark is None:
        floor_mark = next((point.floor_mark for point in reversed(points) if point.floor_mark is not None), None)
    startschuss_low = latest.startschuss_low
    if startschuss_low is None:
        startschuss_low = next((point.startschuss_low for point in reversed(points) if point.startschuss_low is not None), None)
    return anchor_date, floor_mark, startschuss_low


def _legacy_market_action_and_tone(
    phase: str,
    warning_count: int,
    breadth_mode: str,
    vix_regime: str,
) -> tuple[str, str, str]:
    clean_phase = str(phase or "").lower()
    clean_breadth = str(breadth_mode or "").lower()
    clean_vol = str(vix_regime or "").lower()
    if clean_phase == "rot" or warning_count >= 3 or clean_breadth == "schutz" or clean_vol == "stress":
        if clean_phase == "rot":
            message = "Ampel rot. Risiko reduzieren, keine aggressiven Neueinstiege und bestehende Positionen kritisch prüfen."
        elif clean_vol == "stress":
            message = "Volatilität im Stress-Regime. Defensive Haltung - kein Neukauf trotz Ampelphase."
        elif clean_breadth == "schutz":
            message = "Marktbreite im Schutzmodus. Risiko reduzieren - keine aggressiven Neueinstiege."
        else:
            message = f"{warning_count} Warnzeichen aktiv. Defensive Haltung - Risiko reduzieren trotz laufender Ampelphase."
        return "Defensiv", "bad", message
    if clean_phase == "gelb":
        if warning_count <= 2 and clean_breadth != "schutz" and clean_vol not in {"stress", "risk"}:
            return (
                "Startschuss",
                "warning",
                "Startschuss aktiv. Erste Pilotpositionen sind erlaubt, aber nur selektiv und mit enger Risikokontrolle über das Startschuss-Tief.",
            )
        return (
            "Startschuss",
            "warning",
            "Startschuss erkannt, aber Umfeld noch nicht frei. Nur kleine Testpositionen und keine Aggressivität.",
        )
    if clean_phase == "gruen":
        if warning_count <= 2 and clean_breadth != "schutz":
            return (
                "Frühe Bestätigung",
                "good",
                "Startschuss bestätigt. Gute Setups sind erlaubt und Risiko kann vorsichtig erhöht werden.",
            )
        return "Frühe Bestätigung", "warning", "Ampel grün, aber Umfeld gemischt. Nur selektiv aufstocken."
    if clean_phase == "aufwaertstrend":
        return (
            "Offensiv",
            "good",
            "MA-Ordnung bestätigt. Markt konstruktiv, führende Aktien beobachten und Risiko schrittweise erhöhen.",
        )
    if warning_count >= 2 or clean_breadth == "neutral" or clean_vol in {"risk", "vorsicht"}:
        return "Neutral", "warning", "Selektiv bleiben. Nur A-Setups und eher kleine Einstiege."
    return "Konstruktiv", "good", "Markt konstruktiv. Führende Aktien beobachten und Risiko schrittweise erhöhen."


def _ampel_phase_info(
    latest: TrendAmpelPoint,
    *,
    anchor_date: str | None,
    floor_mark: float | None,
    startschuss_low: float | None,
) -> MarketAmpelPhaseInfo:
    phase = latest.phase
    if phase == "rot":
        reason = (
            f"Substanzielle Korrektur läuft. Ankertag: {anchor_date}. Bodenmarke: {_format_number(floor_mark)}."
            if anchor_date and floor_mark is not None
            else "Substanzielle Korrektur läuft. Warte auf Ankertag, also den ersten positiven Schluss."
        )
        return MarketAmpelPhaseInfo(
            phase=phase,
            label="ROT - Abwarten",
            reason=reason,
            action="Nicht kaufen. Beobachte den Markt auf Stabilisierung.",
            tone="bad",
        )
    if phase == "gelb":
        reason = (
            f"Startschuss erkannt. Ankertag: {anchor_date}. Validierungslinie: {_format_number(startschuss_low)}."
            if anchor_date and startschuss_low is not None
            else "Startschuss aktiv."
        )
        return MarketAmpelPhaseInfo(
            phase=phase,
            label="GELB - Startschuss",
            reason=reason,
            action="Erste Positionen eröffnen, aber nur mit klarem Setup und kleiner Größe.",
            tone="warning",
        )
    if phase == "gruen":
        reason = (
            f"Startschuss hält. Kurs bleibt über dem Startschuss-Tief {_format_number(startschuss_low)}."
            if startschuss_low is not None
            else "Startschuss bestätigt."
        )
        return MarketAmpelPhaseInfo(
            phase=phase,
            label="GRÜN - Bestätigung",
            reason=reason,
            action="Frühe Bestätigungsphase. Exponierung vorsichtig aufbauen.",
            tone="good",
        )
    if phase == "aufwaertstrend":
        return MarketAmpelPhaseInfo(
            phase=phase,
            label="AUFWÄRTSTREND",
            reason="Rückenwind aktiv: 21-EMA > 50-SMA > 200-SMA. Fällt 21-EMA unter 50-SMA, geht die Ampel auf Grün zurück.",
            action="Offensiv handeln. Viele kleine Positionen und beste Läufer aufstocken.",
            tone="good",
        )
    return MarketAmpelPhaseInfo(
        phase="neutral",
        label="NEUTRAL",
        reason="Keine substanzielle Korrektur erkannt. Die Trendwende-Ampel ist nicht aktiv.",
        action="Normale Marktbeobachtung. Ampel greift erst bei substanziellem Drawdown.",
        tone="neutral",
    )


def _ampel_lights(phase: str) -> list[MarketAmpelLight]:
    active_key = phase
    rules = {
        "rot": "ROT wird aktiv bei Drawdown von mehr als 10% vom jüngsten Hoch oder Schlusskurs unter der 50-SMA bei mindestens 4 Distribution Days im 25-Tage-Fenster. Nach bestätigter grüner Ampel schaltet zusätzlich ein Schlusskurs unter der 200-SMA auf Rot.",
        "gelb": "GELB wird aktiv, wenn nach einem Ankertag frühestens ab Tag 5 ein Startschuss auftritt: mindestens +1,0%, Volumen über Vortag und kein Unterschreiten der Bodenmarke intraday.",
        "gruen": f"GRÜN wird aktiv, wenn der Startschuss hält und nach GELB mehr als {GREEN_CONFIRMATION_DAYS} weitere Handelstage vergehen, ohne dass das Startschuss-Tief per Schlusskurs gebrochen wird.",
        "aufwaertstrend": f"AUFWÄRTSTREND/RÜCKENWIND wird aktiv, wenn die grüne Phase mindestens {UPTREND_CONFIRMATION_DAYS} Tage Bestand hatte und 21-EMA > 50-SMA > 200-SMA gilt. Ab Grün schaltet ein Schluss unter 200-SMA auf Rot.",
    }
    lights = [
        MarketAmpelLight(key="rot", label="ROT", active=active_key == "rot", rule=rules["rot"], tone="bad"),
        MarketAmpelLight(key="gelb", label="GELB", active=active_key == "gelb", rule=rules["gelb"], tone="warning"),
        MarketAmpelLight(
            key="gruen",
            label="GRÜN",
            active=active_key == "gruen",
            rule=rules["gruen"],
            tone="good",
        ),
        MarketAmpelLight(
            key="aufwaertstrend",
            label="AUFWÄRTSTREND",
            active=active_key == "aufwaertstrend",
            rule=rules["aufwaertstrend"],
            tone="good",
        ),
    ]
    if phase == "neutral":
        return [item.model_copy(update={"active": False}) for item in lights]
    return lights


def _ampel_cycle(
    latest: TrendAmpelPoint,
    *,
    anchor_date: str | None,
    floor_mark: float | None,
    startschuss_low: float | None,
) -> MarketAmpelCycle:
    close = latest.close
    diagnostics = []
    if not anchor_date:
        diagnostics.append("Kein aktiver Ankertag")
    if floor_mark is None:
        diagnostics.append("Bodenmarke noch nicht gesetzt")
    if startschuss_low is None:
        diagnostics.append("Startschuss-Tief noch nicht gesetzt")
    return MarketAmpelCycle(
        anchor_date=anchor_date,
        floor_mark=floor_mark,
        floor_distance_pct=_safe_pct_change(close, floor_mark),
        startschuss_low=startschuss_low,
        startschuss_distance_pct=_safe_pct_change(close, startschuss_low),
        startschuss_bonus=latest.startschuss_bonus,
        ma_order=latest.ma_order,
        diagnostics=diagnostics,
    )


def _ampel_reasons(
    latest: TrendAmpelPoint,
    *,
    warning_count: int,
    breadth_mode: str,
    vix_regime: str,
    anchor_date: str | None,
    floor_mark: float | None,
    startschuss_low: float | None,
) -> list[str]:
    return [
        _ampel_reason_line(latest, anchor_date=anchor_date, floor_mark=floor_mark, startschuss_low=startschuss_low),
        f"Aktive Warnzeichen: {warning_count}",
        f"Abstand zur 50-SMA: {_format_optional_pct(latest.dist_50sma_pct)}",
        f"Equal-Weight-Modus: {breadth_mode.capitalize()}",
        f"VIX-Regime: {vix_regime}",
    ][:4]


def _ampel_reason_line(
    latest: TrendAmpelPoint,
    *,
    anchor_date: str | None,
    floor_mark: float | None,
    startschuss_low: float | None,
) -> str:
    if latest.phase == "gelb":
        if anchor_date and startschuss_low is not None:
            return f"Trendwende-Ampel: GELB - Startschuss aktiv seit {anchor_date} · Startschuss-Tief {_format_number(startschuss_low)}"
        return "Trendwende-Ampel: GELB - Startschuss aktiv"
    if latest.phase == "gruen":
        if startschuss_low is not None:
            return f"Trendwende-Ampel: GRÜN - Startschuss bestätigt · Absicherung über {_format_number(startschuss_low)}"
        return "Trendwende-Ampel: GRÜN - Startschuss bestätigt"
    if latest.phase == "aufwaertstrend":
        return "Trendwende-Ampel: AUFWÄRTSTREND - MA-Ordnung bestätigt"
    if latest.phase == "rot":
        if floor_mark is not None:
            return f"Trendwende-Ampel: ROT - Korrektur aktiv · Floor-Marke {_format_number(floor_mark)}"
        return "Trendwende-Ampel: ROT - Korrektur aktiv"
    return "Trendwende-Ampel: NEUTRAL - kein aktiver Zyklus"


def _ampel_change_cards(
    *,
    latest: TrendAmpelPoint,
    previous: TrendAmpelPoint | None,
    warning_count: int,
    breadth_mode: str,
    volatility: VolatilityResponse,
    index_name: str,
) -> list[MarketAmpelChangeCard]:
    cards: list[MarketAmpelChangeCard] = []
    if latest.pct_change is not None:
        cards.append(
            MarketAmpelChangeCard(
                title=f"Heute {index_name}",
                value=f"{latest.pct_change:+.2f}%",
                detail=f"Schlusskurs {_format_number(latest.close)}",
                detail2=f"Index Stand: {_format_date_de(latest.date)}",
                detail3=f"52W-Hoch: {_format_optional_pct(latest.dist_52w_pct)}",
                tone="good" if latest.pct_change >= 0 else "bad",
                arrow="up" if latest.pct_change >= 0 else "down",
            )
        )
    dist_now = latest.dist_count_25
    dist_prev = previous.dist_count_25 if previous else dist_now
    delta = dist_now - dist_prev
    quality = "Gut" if dist_now < 4 else ("Häufung" if dist_now < 6 else "Kritisch")
    cards.append(
        MarketAmpelChangeCard(
            title="Distribution",
            value=f"{dist_now} aktive Dist.-Tage",
            detail=f"Gegenüber gestern: {delta:+d}" if delta else "Gegenüber gestern: unverändert",
            tone="good" if dist_now < 4 else ("warning" if dist_now < 6 else "bad"),
            quality=quality,
        )
    )
    previous_label = _ampel_phase_label(previous.phase if previous else "")
    phase_label = _ampel_phase_label(latest.phase)
    if latest.phase == "gelb":
        detail = (
            f"Startschuss-Tief {_format_number(latest.startschuss_low)} · {warning_count} Warnzeichen"
            if latest.startschuss_low is not None
            else f"Startschuss aktiv · {warning_count} Warnzeichen"
        )
    elif latest.phase == "gruen":
        detail = f"Startschuss bestätigt · {warning_count} Warnzeichen"
    else:
        detail = (
            f"Wechsel von {previous_label} auf {phase_label}"
            if previous_label != phase_label
            else f"Unverändert seit gestern · {warning_count} Warnzeichen"
        )
    cards.append(
        MarketAmpelChangeCard(
            title="Trendwende-Ampel",
            value=phase_label,
            detail=detail,
            tone=_tone_for_phase(latest.phase),
        )
    )
    vol_latest = volatility.points[-1] if volatility.points else None
    if vol_latest is not None:
        cards.append(
            MarketAmpelChangeCard(
                title="Volatilität",
                value=f"VIX {vol_latest.vix_close:.1f}" if vol_latest.vix_close is not None else "VIX n/a",
                detail=f"Regime: {vol_latest.vix_regime}",
                detail2=f"VIX Stand: {_format_date_de(vol_latest.date)}" if vol_latest.vix_close is not None else None,
                tone=_tone_for_vix_regime(vol_latest.vix_regime),
            )
        )
    cards.append(
        MarketAmpelChangeCard(
            title="Breite",
            value=breadth_mode.capitalize(),
            detail="Equal-Weight als Bestätigung des Indextrends",
            tone=_tone_for_breadth_mode(breadth_mode),
        )
    )
    return cards[:4]


def _ampel_distance_tiles(latest: TrendAmpelPoint, *, index_name: str) -> list[MarketAmpelDistanceTile]:
    d50_threshold = 7.0 if "Nasdaq" in index_name else 5.0
    tiles = []
    if latest.dist_21ema is None:
        tiles.append(_distance_tile("21-EMA Abstand", "-", "-", "neutral", "Kurzfristiger Abstand in ATR-Einheiten"))
    elif latest.dist_21ema < 0:
        tiles.append(
            _distance_tile(
                "21-EMA Abstand",
                f"{latest.dist_21ema:.1f} ATR",
                "Darunter",
                "bad",
                "Kurzfristiger Abstand in ATR-Einheiten",
            )
        )
    elif latest.dist_21ema > 3.0:
        tiles.append(
            _distance_tile(
                "21-EMA Abstand",
                f"{latest.dist_21ema:.1f} ATR",
                "Überdehnt",
                "warning",
                "Kurzfristiger Abstand in ATR-Einheiten",
            )
        )
    else:
        tiles.append(
            _distance_tile(
                "21-EMA Abstand",
                f"{latest.dist_21ema:.1f} ATR",
                "OK",
                "good",
                "Kurzfristiger Abstand in ATR-Einheiten",
            )
        )

    tiles.append(_sma_distance_tile("10-SMA", latest.dist_10sma_pct, "Sehr kurzfristiger Trendabstand"))
    if latest.dist_50sma_pct is None:
        tiles.append(_distance_tile("50-SMA", "-", "-", "neutral", "Mittelfristiger Trendabstand"))
    elif latest.dist_50sma_pct < 0:
        tiles.append(
            _distance_tile(
                "50-SMA",
                f"{latest.dist_50sma_pct:+.1f}%",
                "Darunter",
                "bad",
                "Mittelfristiger Trendabstand",
            )
        )
    elif latest.dist_50sma_pct > d50_threshold:
        tiles.append(
            _distance_tile(
                "50-SMA",
                f"{latest.dist_50sma_pct:+.1f}%",
                "Überdehnt",
                "warning",
                f"Schwelle {d50_threshold:.0f}% für {index_name}",
            )
        )
    else:
        tiles.append(
            _distance_tile(
                "50-SMA",
                f"{latest.dist_50sma_pct:+.1f}%",
                "OK",
                "good",
                "Mittelfristiger Trendabstand",
            )
        )
    tiles.append(_sma_distance_tile("200-SMA", latest.dist_200sma_pct, "Langfristiger Trendabstand"))
    return tiles


def _build_ampel_warning_checks(
    *,
    points: Sequence[TrendAmpelPoint],
    latest: TrendAmpelPoint,
    intermarket: list[MarketIntermarketItem],
    defensive_lead: bool | None,
    defensive_spread_pct: float | None,
    index_name: str,
) -> list[MarketAmpelWarningCheck]:
    checks: list[MarketAmpelWarningCheck] = []
    neg_reversals = latest.neg_reversals_10d
    pos_reversals = latest.pos_reversals_10d
    checks.append(
        _ampel_warning_check(
            "Bärische Intraday-Umkehrungen (10T)",
            neg_reversals < 3,
            f"{neg_reversals} neg. / {pos_reversals} pos. Umkehrungen",
            neg_reversals >= 3,
        )
    )
    low_cr_5d = latest.low_cr_5d
    checks.append(
        _ampel_warning_check(
            "Closing Range Häufung (5T)",
            low_cr_5d < 3,
            f"{low_cr_5d}/5 Tage Schluss im unteren 25%",
            low_cr_5d >= 3,
        )
    )
    stall_10d = sum(1 for point in points[-10:] if point.is_stall)
    checks.append(
        _ampel_warning_check("Stau-Tage (10T)", stall_10d < 3, f"{stall_10d} Stau-Tage", stall_10d >= 3)
    )
    dist_count = latest.dist_count_25
    checks.append(
        _ampel_warning_check(
            "Distributionstage (25T)",
            dist_count < 4,
            f"{dist_count} Dist.-Tage (Schwelle: 4)",
            dist_count >= 4,
        )
    )
    loss_gain_ratio = latest.loss_gain_ratio_10d or 0.0
    loss_day_warning = loss_gain_ratio >= 3.0
    loss_day_critical = loss_gain_ratio >= 4.0
    checks.append(
        _ampel_warning_check(
            "Verlusttage/Gewinntage (10T)",
            not loss_day_warning,
            f"{latest.loss_days_10d} Verlusttage / {latest.gain_days_10d} Gewinntage · Verhältnis {loss_gain_ratio:.1f}:1",
            loss_day_warning,
            tone="bad" if loss_day_critical else "warning",
        )
    )
    d50_threshold = 7.0 if "Nasdaq" in index_name else 5.0
    if latest.dist_50sma_pct is not None:
        d50_warning = latest.dist_50sma_pct > d50_threshold or latest.dist_50sma_pct < 0
        checks.append(
            _ampel_warning_check(
                "50-SMA Abstand",
                not d50_warning,
                f"{latest.dist_50sma_pct:+.1f}% ({'über' if latest.dist_50sma_pct > 0 else 'unter'} 50-SMA, Schwelle: {d50_threshold:.0f}%)",
                d50_warning,
            )
        )
    if latest.dist_21ema is not None:
        under_21 = latest.dist_21ema < 0
        over_21 = latest.dist_21ema > 3.0
        checks.append(
            _ampel_warning_check(
                "Kurs unter 21-EMA",
                not under_21,
                f"{latest.dist_21ema:.1f} ATR unter 21-EMA" if under_21 else f"{latest.dist_21ema:.1f} ATR über 21-EMA",
                under_21,
            )
        )
        checks.append(
            _ampel_warning_check(
                "Überdehnt über 21-EMA (>3 ATR)",
                not over_21,
                f"{latest.dist_21ema:.1f} ATR über 21-EMA",
                over_21,
            )
        )
    under_200 = latest.sma200 is not None and latest.close is not None and latest.close < latest.sma200
    under_50 = latest.sma50 is not None and latest.close is not None and latest.close < latest.sma50
    checks.append(_ampel_warning_check("Kurs über 200-SMA", not under_200, "Unter 200-SMA" if under_200 else "OK", under_200))
    checks.append(_ampel_warning_check("Kurs über 50-SMA", not under_50, "Unter 50-SMA" if under_50 else "OK", under_50))
    declining_up_volume = bool(latest.up_vol_declining)
    checks.append(
        _ampel_warning_check(
            "Volumen an Aufwärtstagen",
            not declining_up_volume,
            "Abnehmendes Vol." if declining_up_volume else "OK",
            declining_up_volume,
        )
    )
    intermarket_divergence = _has_intermarket_divergence(intermarket)
    if intermarket:
        checks.append(
            _ampel_warning_check(
                "Intermarket-Konvergenz",
                not intermarket_divergence,
                _intermarket_detail(intermarket),
                intermarket_divergence,
            )
        )
    if defensive_lead is not None:
        checks.append(
            _ampel_warning_check(
                "Keine Sektorrotation in Defensive",
                not defensive_lead,
                f"Spread: {_format_optional_pct(defensive_spread_pct)}",
                bool(defensive_lead),
            )
        )
    recovery_pct, drop_pct = _detect_failing_rally(points)
    if recovery_pct is not None and drop_pct is not None and drop_pct > 5:
        weak_recovery = recovery_pct < 50
        checks.append(
            _ampel_warning_check(
                "Erholungsquote >=50%",
                not weak_recovery,
                f"Rückgang {drop_pct:.1f}%, Erholung {recovery_pct:.0f}%",
                weak_recovery,
            )
        )
    return checks


def _ampel_warning_check(
    label: str,
    passed: bool,
    detail: str,
    active_warning: bool,
    *,
    tone: str | None = None,
) -> MarketAmpelWarningCheck:
    return MarketAmpelWarningCheck(
        label=label,
        passed=passed,
        detail=detail,
        active_warning=active_warning,
        tone="good" if passed else tone or "warning",
    )


def _ampel_chart_points(points: Sequence[TrendAmpelPoint]) -> list[MarketAmpelChartPoint]:
    return [
        MarketAmpelChartPoint(
            date=point.date,
            open=point.open,
            high=point.high,
            low=point.low,
            close=point.close,
            volume=point.volume,
            ema21=point.ema21,
            sma10=point.sma10,
            sma50=point.sma50,
            sma200=point.sma200,
            vol_sma50=point.vol_sma50,
            dist_52w_pct=point.dist_52w_pct,
            consec_low_above_21=point.consec_low_above_21,
            consec_low_above_50=point.consec_low_above_50,
            consec_low_above_200=point.consec_low_above_200,
            ema21_held=bool(point.ema21_held),
            sma50_held=bool(point.sma50_held),
            sma200_held=bool(point.sma200_held),
            up_vol_declining=bool(point.up_vol_declining),
            phase=point.phase,
            is_distribution=bool(point.is_distribution),
            is_stall=bool(point.is_stall),
            intraday_reversal_down=bool(point.intraday_reversal_down),
            intraday_reversal_up=bool(point.intraday_reversal_up),
        )
        for point in points
    ]


def _ampel_chart_markers(
    chart_points: Sequence[MarketAmpelChartPoint],
    latest: TrendAmpelPoint,
    *,
    anchor_date: str | None,
    floor_mark: float | None,
) -> list[MarketAmpelChartMarker]:
    markers: list[MarketAmpelChartMarker] = []
    if anchor_date:
        markers.append(MarketAmpelChartMarker(key="anchor", date=anchor_date, label="Ankertag", color="#f59e0b"))
    for point in chart_points:
        if point.is_distribution:
            markers.append(
                MarketAmpelChartMarker(
                    key=f"dist-{point.date}",
                    date=point.date,
                    label="Dist.",
                    value=point.close,
                    color="#fb7185",
                )
            )
        elif point.is_stall:
            markers.append(
                MarketAmpelChartMarker(
                    key=f"stall-{point.date}",
                    date=point.date,
                    label="Stau",
                    value=point.close,
                    color="#fbbf24",
                )
            )
    if floor_mark is not None and latest.phase == "rot":
        markers.append(
            MarketAmpelChartMarker(
                key="floor",
                date=latest.date,
                label=f"Floor {_format_number(floor_mark)}",
                value=floor_mark,
                color="#f87171",
            )
        )
    return markers[-8:]


def _detect_failing_rally(points: Sequence[TrendAmpelPoint]) -> tuple[float | None, float | None]:
    clean = [point for point in points if point.close is not None]
    if len(clean) < 30:
        return None, None
    recent = clean[-60:]
    high_point = max(recent, key=lambda point: point.close or 0)
    high_index = recent.index(high_point)
    after_high = recent[high_index:]
    if len(after_high) < 5 or high_point.close is None:
        return None, None
    low_point = min(after_high, key=lambda point: point.close or float("inf"))
    if low_point.close is None or high_point.close <= 0:
        return None, None
    drop = high_point.close - low_point.close
    if drop / high_point.close < 0.03:
        return None, None
    latest_close = clean[-1].close
    if latest_close is None:
        return None, None
    recovery = latest_close - low_point.close
    return round(recovery / drop * 100, 1), round(drop / high_point.close * 100, 1)


def _volatility_card_status(volatility: VolatilityResponse, title: str) -> str:
    for card in volatility.status_cards:
        if card.title == title:
            return card.status
    return "n/a"


def _distance_tile(label: str, value: str, indicator: str, tone: str, detail: str) -> MarketAmpelDistanceTile:
    return MarketAmpelDistanceTile(label=label, value=value, indicator=indicator, tone=tone, detail=detail)


def _sma_distance_tile(label: str, value: float | None, detail: str) -> MarketAmpelDistanceTile:
    if value is None:
        return _distance_tile(label, "-", "-", "neutral", detail)
    if value < 0:
        return _distance_tile(label, f"{value:+.1f}%", "Darunter", "bad", detail)
    return _distance_tile(label, f"{value:+.1f}%", "OK", "good", detail)


def _ampel_phase_label(phase: str) -> str:
    return {
        "rot": "ROT",
        "gelb": "GELB - Startschuss",
        "gruen": "GRÜN - Frühe Bestätigung",
        "aufwaertstrend": "AUFWÄRTSTREND",
        "neutral": "NEUTRAL",
    }.get(str(phase or "").lower(), str(phase or "-").upper())


def _tone_for_phase(phase: str) -> str:
    if phase in {"gruen", "aufwaertstrend"}:
        return "good"
    if phase in {"gelb", "neutral"}:
        return "warning"
    return "bad"


def _tone_for_breadth_mode(mode: str) -> str:
    if mode == "rueckenwind":
        return "good"
    if mode == "wachsam":
        return "warning"
    return "bad"


def _tone_for_vix_regime(regime: str) -> str:
    if regime == "Stress":
        return "bad"
    if regime == "Ruhig":
        return "good"
    if regime == "Neutral":
        return "neutral"
    return "warning"


def _format_number(value: float | None, *, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def _format_date_de(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


def _normalize_tickers(tickers: list[str]) -> list[str]:
    return list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))


def _normalize_phase(value: str) -> str:
    if value in {"rot", "gelb", "gruen", "aufwaertstrend", "neutral"}:
        return value
    return "neutral"


def _normalize_breadth_mode(value: str) -> str:
    if value in {"schutz", "wachsam", "rueckenwind"}:
        return value
    return "wachsam"


def _phase_label(phase: str) -> str:
    return {
        "rot": "Rot",
        "gelb": "Gelb",
        "gruen": "Grün",
        "aufwaertstrend": "Aufwärtstrend",
        "neutral": "Neutral",
    }.get(phase, "Neutral")


def _action_for_phase(phase: str) -> str:
    if phase == "rot":
        return "Defensiv bleiben, neue Käufe stark filtern und Risiko reduzieren."
    if phase == "gelb":
        return "Wachsam bleiben, Positionsgrößen kontrollieren und Breakouts nur selektiv handeln."
    if phase == "gruen":
        return "Konstruktiv bleiben, Qualitäts-Setups bevorzugen und Stops diszipliniert nachziehen."
    return "Marktdaten prüfen und keine großen Risikoänderungen ohne frische Breitenwerte vornehmen."


def _kpis_from_metrics(metrics: dict) -> list[KpiCard]:
    raw_kpis = metrics.get("kpis")
    if isinstance(raw_kpis, list) and raw_kpis:
        return [KpiCard.model_validate(item) for item in raw_kpis]
    return [
        KpiCard(label="Coverage", value=_format_pct(float(metrics.get("coverage_ratio") or 0) * 100), detail="Universe", tone="neutral"),
        KpiCard(label="Adv/Decl", value=f"{metrics.get('advancers', 0)}/{metrics.get('decliners', 0)}", detail="letzter Tag", tone="neutral"),
        KpiCard(label="McClellan", value=f"{float(metrics.get('mcclellan') or 0):+.1f}", detail="A/D Momentum", tone="neutral"),
        KpiCard(label="New Highs/Lows", value=f"{metrics.get('new_highs', 0)}/{metrics.get('new_lows', 0)}", detail="52W Proxy", tone="neutral"),
    ]


def _trend_bar_from_ohlcv(point: MarketOhlcvPoint) -> TrendAmpelBar:
    return TrendAmpelBar(
        date=point.date,
        open=point.open,
        high=point.high,
        low=point.low,
        close=point.close,
        volume=point.volume,
    )


def _trend_ampel_metrics(point: TrendAmpelPoint | None, *, ticker: str) -> dict:
    if point is None:
        return {"ticker": ticker, "source": "missing", "message": "Keine Benchmark-OHLCV-Daten im Cache."}
    return {
        "ticker": ticker,
        "source": "database",
        "as_of": point.date,
        "phase": point.phase,
        "phase_label": _phase_label(point.phase),
        "close": point.close,
        "anchor_date": point.anchor_date,
        "floor_mark": point.floor_mark,
        "startschuss_low": point.startschuss_low,
        "startschuss_bonus": point.startschuss_bonus,
        "dist_count_25": point.dist_count_25,
    }


def _trend_ampel_from_metrics(metrics: dict) -> MarketTrendAmpel | None:
    raw = metrics.get("trend_ampel")
    if not isinstance(raw, dict) or raw.get("source") == "missing":
        return None
    return MarketTrendAmpel.model_validate(raw)


def _combined_market_action(
    *,
    trend_phase: str,
    breadth_action: str,
    breadth_mode: str,
    volatility_regime: str,
) -> str:
    trend_action = _action_for_phase(trend_phase)
    if trend_phase == "rot":
        return f"Trend-Ampel Rot. {trend_action}"
    if volatility_regime == "Risk Off bestätigt":
        return f"Trend-Ampel {_phase_label(trend_phase)}; Volatilität bestätigt Stress. Risiko nicht erhöhen."
    if breadth_mode == "schutz":
        return f"Trend-Ampel {_phase_label(trend_phase)}; Marktbreite im Schutzmodus. {breadth_action}"
    return f"Trend-Ampel {_phase_label(trend_phase)}. {breadth_action}"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def _data_status_for_date(value: date) -> str:
    age_days = (date.today() - value).days
    if age_days < 0:
        return "fresh"
    if age_days <= 3:
        return "fresh"
    if age_days <= 10:
        return "stale"
    return "stale"


def _market_snapshot_message(snapshot_date: date, metrics: dict) -> str:
    status = _data_status_for_date(snapshot_date)
    coverage = float(metrics.get("coverage_ratio") or 0)
    prefix = "MarketSnapshot aus Postgres"
    if status == "stale":
        prefix = "MarketSnapshot ist älter"
    return f"{prefix}; Coverage {_format_pct(coverage * 100)}. Bei Bedarf refresh_prices und refresh_breadth starten."


def _breadth_metadata_with_legacy_fallback(rows: Sequence) -> dict:
    latest_meta = dict(rows[-1].metadata_json or {}) if rows else {}
    historic_loaded_universe = max(
        (
            int((row.metadata_json or {}).get("loaded_universe") or (row.metadata_json or {}).get("covered_count") or 0)
            for row in rows
        ),
        default=0,
    )
    if "loaded_universe" not in latest_meta and historic_loaded_universe:
        latest_meta["loaded_universe"] = historic_loaded_universe
    requested_raw = latest_meta.get("universe_size") or latest_meta.get("requested_universe")
    try:
        requested = int(requested_raw) if requested_raw else 0
    except (TypeError, ValueError):
        requested = 0
    loaded = int(latest_meta.get("loaded_universe") or 0)
    if requested and loaded and ("coverage_ratio" not in latest_meta or not latest_meta.get("coverage_ratio")):
        latest_meta["coverage_ratio"] = loaded / requested
    return latest_meta


def _metadata_int(metadata: Mapping[str, object], *keys: str) -> int:
    for key in keys:
        value = metadata.get(key)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _breadth_message(breadth_date: date, metadata: dict) -> str:
    status = _data_status_for_date(breadth_date)
    loaded = int(metadata.get("loaded_universe") or metadata.get("covered_count") or 0)
    daily_covered = int(metadata.get("daily_covered_count") or metadata.get("covered_count") or 0)
    universe_size = int(metadata.get("universe_size") or 0)
    coverage = float(metadata.get("coverage_ratio") or 0)
    prefix = "Breitenwerte aus Postgres"
    if status == "stale":
        prefix = "Breitenwerte sind älter"
    daily_note = f", letzter Tag {daily_covered} Titel" if daily_covered and daily_covered != loaded else ""
    return f"{prefix}; Coverage {_format_pct(coverage * 100)} ({loaded}/{universe_size}{daily_note})."


def _pct(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total * 100


def _ema(value: float, *, previous: float | None, period: int) -> float:
    alpha = 2 / (period + 1)
    return value if previous is None else alpha * value + (1 - alpha) * previous


def _point_high(point: MarketPricePoint | MarketOhlcvPoint) -> float:
    return float(getattr(point, "high", point.close) or point.close)


def _point_low(point: MarketPricePoint | MarketOhlcvPoint) -> float:
    return float(getattr(point, "low", point.close) or point.close)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _trailing_return(values: list[float | None], periods: int) -> float | None:
    if len(values) <= periods:
        return None
    current = values[-1]
    previous = values[-1 - periods]
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1) * 100
