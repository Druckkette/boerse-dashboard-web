from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_KEY, DEFAULT_MARKET_UNIVERSE_TICKERS
from app.domain.market.regime import MarketRegimeInput, classify_market_regime
from app.domain.market.volatility import (
    VOLATILITY_TICKERS,
    compute_volatility_dashboard,
    summarize_volatility_points,
)
from app.repositories import market as market_repository
from app.repositories.market import (
    BreadthDailyWrite,
    MarketPricePoint,
    MarketRepositoryUnavailable,
    MarketSnapshotWrite,
)
from app.schemas import BreadthPoint, BreadthResponse, KpiCard, MarketOverviewResponse, VolatilityPoint, VolatilityResponse, VolatilityStatusCard
from app.services.dummy_data import get_breadth as get_dummy_breadth
from app.services.dummy_data import get_market_overview as get_dummy_market_overview


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
        return get_dummy_market_overview()

    metrics = snapshot.metrics_json or {}
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
        kpis=_kpis_from_metrics(metrics),
    )


def get_breadth(universe: str = DEFAULT_MARKET_UNIVERSE_KEY, *, limit: int = 160) -> BreadthResponse:
    try:
        rows = market_repository.list_breadth_daily(universe=universe, limit=limit)
    except MarketRepositoryUnavailable:
        rows = []

    if not rows:
        return get_dummy_breadth()

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
    snapshot = build_market_snapshot(computed[-1], volatility_summary=volatility_summary)
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


def build_market_snapshot(point: BreadthComputationPoint, volatility_summary: dict | None = None) -> MarketSnapshotWrite:
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
    return MarketSnapshotWrite(
        date=point.date,
        ampel_phase=regime.phase,
        warning_count=regime.warning_count,
        breadth_mode=regime.breadth_mode,
        volatility_regime=volatility_regime,
        metrics_json=regime.metrics,
    )


def _cached_volatility_points(*, limit: int = 180):
    start_date = date.today() - timedelta(days=900)
    series = market_repository.load_cached_prices(VOLATILITY_TICKERS, start_date=start_date)
    return compute_volatility_dashboard(series, limit=limit)


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
    return {"rot": "Rot", "gelb": "Gelb", "gruen": "Grün"}.get(phase, "Neutral")


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
