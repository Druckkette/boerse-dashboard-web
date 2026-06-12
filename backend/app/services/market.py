from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.market.ampel import TrendAmpelBar, TrendAmpelPoint, compute_trend_ampel
from app.domain.market.constants import (
    DEFAULT_MARKET_UNIVERSE_KEY,
    DEFAULT_MARKET_UNIVERSE_TICKERS,
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


MARKET_TREND_BENCHMARK = "SPY"
INTERMARKET_INDEXES = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
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
    covered_count: int


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
        )
        for row in rows
    ]
    latest_meta = rows[-1].metadata_json or {}
    return BreadthResponse(
        as_of=points[-1].date,
        universe=universe,
        source="database",
        data_status=_data_status_for_date(rows[-1].date),
        message=_breadth_message(rows[-1].date, latest_meta),
        coverage_ratio=float(latest_meta.get("coverage_ratio") or 0),
        points=points,
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
    series = market_repository.load_cached_prices(clean_tickers, start_date=start_date)
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
                "covered_count": point.covered_count,
            },
        )
        for point in computed
    ]
    rows_written = market_repository.upsert_breadth_daily(writes)
    volatility_points = _cached_volatility_points(limit=180)
    volatility_summary = summarize_volatility_points(volatility_points)
    trend_point = _latest_cached_trend_ampel_point(MARKET_TREND_BENCHMARK, lookback_days=lookback_days)
    snapshot = build_market_snapshot(
        computed[-1],
        volatility_summary=volatility_summary,
        trend_point=trend_point,
        trend_ticker=MARKET_TREND_BENCHMARK,
    )
    market_repository.upsert_market_snapshot(snapshot)
    return {
        "ok": True,
        "universe": universe,
        "universe_size": len(clean_tickers),
        "covered_tickers": len(series),
        "records_seen": sum(len(points) for points in series.values()),
        "records_written": rows_written + 1,
        "breadth_rows_written": rows_written,
        "snapshot_date": computed[-1].date.isoformat(),
        "coverage_ratio": computed[-1].coverage_ratio,
        "phase": snapshot.ampel_phase,
        "trend_phase": trend_point.phase if trend_point else None,
        "volatility_regime": snapshot.volatility_regime,
    }


def compute_breadth_series(
    series: Mapping[str, list[MarketPricePoint]],
    *,
    universe: str,
    universe_size: int | None = None,
) -> list[BreadthComputationPoint]:
    clean_series = {
        ticker: sorted(points, key=lambda point: point.date)
        for ticker, points in series.items()
        if len(points) >= 2
    }
    total_universe_size = universe_size or len(clean_series)
    if not clean_series or total_universe_size <= 0:
        return []

    histories: dict[str, list[MarketPricePoint]] = {ticker: [] for ticker in clean_series}
    by_date: dict[date, dict[str, MarketPricePoint]] = {}
    for ticker, points in clean_series.items():
        for point in points:
            by_date.setdefault(point.date, {})[ticker] = point

    ad_line = 0.0
    ema_19: float | None = None
    ema_39: float | None = None
    computed: list[BreadthComputationPoint] = []

    for current_date in sorted(by_date):
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

            high_low_window = closes_with_current[-252:]
            if len(high_low_window) >= 20:
                new_highs += int(point.close >= max(high_low_window))
                new_lows += int(point.close <= min(high_low_window))
            history.append(point)

        net_advances = advancers - decliners
        ad_line += net_advances
        ema_19 = _ema(net_advances, previous=ema_19, period=19)
        ema_39 = _ema(net_advances, previous=ema_39, period=39)
        mcclellan = ema_19 - ema_39
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
                coverage_ratio=covered_count / total_universe_size,
                universe_size=total_universe_size,
                covered_count=covered_count,
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
        high_window = points[-21:-1]
        reference_high = max((point.high for point in high_window), default=None)
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
            covered_count=point.covered_count,
            volatility_regime=volatility_regime,
            volatility_summary=volatility_summary or {},
        )
    )
    trend_ampel = _trend_ampel_metrics(trend_point, ticker=trend_ticker)
    metrics = {
        **regime.metrics,
        "breadth_phase": regime.phase,
        "trend_ampel": trend_ampel,
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
    bars = market_repository.load_cached_ohlcv(ticker, start_date=start_date)
    if len(bars) < 2:
        return None
    points = compute_trend_ampel([_trend_bar_from_ohlcv(point) for point in bars])
    return points[-1] if points else None


def _cached_volatility_points(*, limit: int = 180):
    start_date = date.today() - timedelta(days=900)
    series = market_repository.load_cached_prices(VOLATILITY_TICKERS, start_date=start_date)
    return compute_volatility_dashboard(series, limit=limit)


def _cached_intermarket_divergence() -> list[MarketIntermarketItem]:
    start_date = date.today() - timedelta(days=120)
    try:
        series = {
            ticker: market_repository.load_cached_ohlcv(ticker, start_date=start_date)
            for ticker in INTERMARKET_INDEXES
        }
    except MarketRepositoryUnavailable:
        return []
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
    try:
        series = market_repository.load_cached_prices(
            [MARKET_TREND_BENCHMARK],
            start_date=date.today() - timedelta(days=420),
        ).get(MARKET_TREND_BENCHMARK, [])
    except MarketRepositoryUnavailable:
        return None
    if not series:
        return None
    closes = [point.close for point in series if point.close > 0]
    if not closes:
        return None
    high = max(closes)
    if high <= 0:
        return None
    return (closes[-1] / high - 1) * 100


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


def _breadth_message(breadth_date: date, metadata: dict) -> str:
    status = _data_status_for_date(breadth_date)
    covered = int(metadata.get("covered_count") or 0)
    universe_size = int(metadata.get("universe_size") or 0)
    coverage = float(metadata.get("coverage_ratio") or 0)
    prefix = "Breitenwerte aus Postgres"
    if status == "stale":
        prefix = "Breitenwerte sind älter"
    return f"{prefix}; Coverage {_format_pct(coverage * 100)} ({covered}/{universe_size})."


def _pct(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total * 100


def _ema(value: float, *, previous: float | None, period: int) -> float:
    alpha = 2 / (period + 1)
    return value if previous is None else alpha * value + (1 - alpha) * previous


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
