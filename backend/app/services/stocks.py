from __future__ import annotations

from datetime import date, datetime, timedelta

from app.domain.stocks.assessment import StockAssessmentResult, compute_stock_assessment
from app.repositories import fundamentals as fundamentals_repository
from app.repositories import prices as price_repository
from app.repositories import relative_strength as rs_repository
from app.repositories import sec13f as sec13f_repository
from app.repositories.fundamentals import (
    FundamentalSnapshotRow,
    FundamentalSnapshotWrite,
    FundamentalsRepositoryUnavailable,
)
from app.repositories.prices import PriceRepositoryUnavailable
from app.repositories.relative_strength import RelativeStrengthRepositoryUnavailable, RsRatingRow
from app.repositories.sec13f import Institutional13FTrendRow, Sec13FRepositoryUnavailable
from app.schemas import (
    StockEarningsWarning,
    StockAssessmentCheck,
    StockAssessmentMetrics,
    StockAssessmentRankingItem,
    StockAssessmentRankingResponse,
    StockAssessmentResponse,
    StockAssessmentScores,
    StockAssessmentSignal,
    StockFundamentalsItem,
    StockFundamentalsResponse,
    StockFundamentalsUpdateRequest,
)


ASSESSMENT_LOOKBACK_DAYS = 740


def get_stock_assessment(ticker: str) -> StockAssessmentResponse:
    clean = ticker.strip().upper()
    start_date = date.today() - timedelta(days=ASSESSMENT_LOOKBACK_DAYS)
    try:
        bars = price_repository.list_price_bars(clean, start_date=start_date)
    except PriceRepositoryUnavailable:
        bars = []

    try:
        rs_row = rs_repository.get_latest_rs_rating(clean, source="computed")
    except RelativeStrengthRepositoryUnavailable:
        rs_row = None

    fundamentals_row = _safe_latest_fundamentals(clean)
    institutional_row = _safe_latest_13f(clean)
    result = compute_stock_assessment(
        clean,
        bars,
        rs_context=_rs_context(rs_row),
        fundamentals_context=_fundamentals_context(fundamentals_row),
        institutional_context=_institutional_context(institutional_row),
    )
    return _to_response(result)


def get_stock_assessment_ranking(*, limit: int = 50) -> StockAssessmentRankingResponse:
    try:
        rs_rows = rs_repository.list_latest_rs_ratings(limit=max(1, min(120, limit)), source="computed")
    except RelativeStrengthRepositoryUnavailable:
        rs_rows = []
    if not rs_rows:
        return StockAssessmentRankingResponse(as_of=date.today().isoformat(), source="missing", rows=[])

    rows: list[StockAssessmentRankingItem] = []
    for rs_row in rs_rows:
        start_date = date.today() - timedelta(days=ASSESSMENT_LOOKBACK_DAYS)
        try:
            bars = price_repository.list_price_bars(rs_row.ticker, start_date=start_date)
        except PriceRepositoryUnavailable:
            bars = []
        fundamentals_row = _safe_latest_fundamentals(rs_row.ticker)
        institutional_row = _safe_latest_13f(rs_row.ticker)
        result = compute_stock_assessment(
            rs_row.ticker,
            bars,
            rs_context=_rs_context(rs_row),
            fundamentals_context=_fundamentals_context(fundamentals_row),
            institutional_context=_institutional_context(institutional_row),
        )
        if result.source != "database":
            continue
        rows.append(_to_ranking_item(result, rs_row.name))

    rows.sort(key=lambda item: (item.overall_score, item.technical_score, item.rs_rating or 0), reverse=True)
    return StockAssessmentRankingResponse(
        as_of=rows[0].as_of if rows else rs_rows[0].date.isoformat(),
        source="database" if rows else "missing",
        rows=rows,
    )


def get_stock_fundamentals(ticker: str) -> StockFundamentalsResponse:
    clean = ticker.strip().upper()
    row = _safe_latest_fundamentals(clean)
    if row is None:
        return StockFundamentalsResponse(ticker=clean, source="missing", item=None)
    return StockFundamentalsResponse(ticker=clean, source="database", item=_fundamental_item(row))


def update_stock_fundamentals(
    ticker: str,
    request: StockFundamentalsUpdateRequest,
) -> StockFundamentalsResponse:
    clean = ticker.strip().upper()
    as_of = _parse_iso_date(request.as_of) or date.today()
    next_earnings = _parse_iso_date(request.next_earnings_date)
    row = fundamentals_repository.upsert_fundamentals(
        FundamentalSnapshotWrite(
            ticker=clean,
            as_of=as_of,
            source=request.source.strip() or "manual",
            fiscal_period=request.fiscal_period.strip(),
            quarterly_eps_growth_pct=request.quarterly_eps_growth_pct,
            annual_eps_growth_pct=request.annual_eps_growth_pct,
            quarterly_revenue_growth_pct=request.quarterly_revenue_growth_pct,
            annual_revenue_growth_pct=request.annual_revenue_growth_pct,
            roe_pct=request.roe_pct,
            profit_margin_pct=request.profit_margin_pct,
            trailing_eps=request.trailing_eps,
            quarterly_eps_accelerating=request.quarterly_eps_accelerating,
            quarterly_revenue_accelerating=request.quarterly_revenue_accelerating,
            institutional_holders=request.institutional_holders,
            institutional_ownership_pct=request.institutional_ownership_pct,
            next_earnings_date=next_earnings,
            beta=request.beta,
            metadata_json={"entered_via": "web"},
        )
    )
    return StockFundamentalsResponse(ticker=clean, source="database", item=_fundamental_item(row))


def _rs_context(row: RsRatingRow | None) -> dict:
    if row is None:
        return {}
    metadata = row.metadata_json or {}
    return {
        "rating": row.rating,
        "percentile": row.percentile,
        "score": row.score,
        "method": row.method,
        "source": row.source,
        "universe_size": row.universe_size,
        "ret_1m_pct": metadata.get("ret_1m_pct"),
        "ret_3m_pct": metadata.get("ret_3m_pct"),
        "ret_6m_pct": metadata.get("ret_6m_pct"),
        "ret_12m_pct": metadata.get("ret_12m_pct"),
        "excess_return_3m_pct": metadata.get("excess_return_3m_pct"),
        "excess_return_6m_pct": metadata.get("excess_return_6m_pct"),
        "excess_return_12m_pct": metadata.get("excess_return_12m_pct"),
        "rs_line_last": metadata.get("rs_line_last"),
        "above_21": metadata.get("above_21"),
        "above_50": metadata.get("above_50"),
        "above_200": metadata.get("above_200"),
        "trend_5w": metadata.get("trend_5w"),
        "trend_13w": metadata.get("trend_13w"),
        "distance_to_high_pct": metadata.get("distance_to_high_pct"),
        "near_high_52w": metadata.get("near_high_52w"),
        "new_high_52w": metadata.get("new_high_52w"),
    }


def _safe_latest_fundamentals(ticker: str) -> FundamentalSnapshotRow | None:
    try:
        return fundamentals_repository.get_latest_fundamentals(ticker)
    except FundamentalsRepositoryUnavailable:
        return None


def _safe_latest_13f(ticker: str) -> Institutional13FTrendRow | None:
    try:
        return sec13f_repository.get_latest_trend_for_ticker(ticker)
    except Sec13FRepositoryUnavailable:
        return None


def _fundamentals_context(row: FundamentalSnapshotRow | None) -> dict:
    if row is None:
        return {}
    return {
        "ticker": row.ticker,
        "as_of": row.as_of.isoformat(),
        "source": row.source,
        "fiscal_period": row.fiscal_period,
        "quarterly_eps_growth_pct": row.quarterly_eps_growth_pct,
        "annual_eps_growth_pct": row.annual_eps_growth_pct,
        "quarterly_revenue_growth_pct": row.quarterly_revenue_growth_pct,
        "annual_revenue_growth_pct": row.annual_revenue_growth_pct,
        "roe_pct": row.roe_pct,
        "profit_margin_pct": row.profit_margin_pct,
        "trailing_eps": row.trailing_eps,
        "quarterly_eps_accelerating": row.quarterly_eps_accelerating,
        "quarterly_revenue_accelerating": row.quarterly_revenue_accelerating,
        "institutional_holders": row.institutional_holders,
        "institutional_ownership_pct": row.institutional_ownership_pct,
        "next_earnings_date": row.next_earnings_date.isoformat() if row.next_earnings_date else None,
        "beta": row.beta,
    }


def _institutional_context(row: Institutional13FTrendRow | None) -> dict:
    if row is None:
        return {}
    raw = row.raw_json or {}
    return {
        "ticker": row.ticker,
        "report_period": raw.get("period") or row.report_period.isoformat(),
        "holder_count": raw.get("holder_count") or row.holders_count,
        "holder_count_delta": raw.get("holder_count_delta"),
        "large_holder_count": raw.get("large_holder_count"),
        "large_holder_delta": raw.get("large_holder_delta"),
        "trend": raw.get("trend"),
    }


def _fundamental_item(row: FundamentalSnapshotRow) -> StockFundamentalsItem:
    return StockFundamentalsItem(
        ticker=row.ticker,
        as_of=row.as_of.isoformat(),
        source=row.source,
        fiscal_period=row.fiscal_period,
        quarterly_eps_growth_pct=row.quarterly_eps_growth_pct,
        annual_eps_growth_pct=row.annual_eps_growth_pct,
        quarterly_revenue_growth_pct=row.quarterly_revenue_growth_pct,
        annual_revenue_growth_pct=row.annual_revenue_growth_pct,
        roe_pct=row.roe_pct,
        profit_margin_pct=row.profit_margin_pct,
        trailing_eps=row.trailing_eps,
        quarterly_eps_accelerating=row.quarterly_eps_accelerating,
        quarterly_revenue_accelerating=row.quarterly_revenue_accelerating,
        institutional_holders=row.institutional_holders,
        institutional_ownership_pct=row.institutional_ownership_pct,
        next_earnings_date=row.next_earnings_date.isoformat() if row.next_earnings_date else None,
        beta=row.beta,
    )


def _to_response(result: StockAssessmentResult) -> StockAssessmentResponse:
    fundamentals = result.fundamentals
    return StockAssessmentResponse(
        ticker=result.ticker,
        as_of=result.as_of,
        source=result.source,
        data_status=result.data_status,
        message=result.message,
        verdict_label=result.verdict_label,
        verdict_tone=result.verdict_tone,
        verdict_text=result.verdict_text,
        fundamentals_available=result.fundamentals_available,
        scores=StockAssessmentScores(
            overall=result.scores.overall,
            technical=result.scores.technical,
            fundamental=result.scores.fundamental,
            moving_averages=result.scores.moving_averages,
            chart_behavior=result.scores.chart_behavior,
        ),
        metrics=StockAssessmentMetrics(
            last_close=result.metrics.last_close,
            change_pct=result.metrics.change_pct,
            atr_pct=result.metrics.atr_pct,
            volume_ratio_50d=result.metrics.volume_ratio_50d,
            dollar_volume_mio=result.metrics.dollar_volume_mio,
            cmf_20=result.metrics.cmf_20,
            drawdown_52w_pct=result.metrics.drawdown_52w_pct,
            distance_sma10_pct=result.metrics.distance_sma10_pct,
            distance_ema21_pct=result.metrics.distance_ema21_pct,
            distance_sma50_pct=result.metrics.distance_sma50_pct,
            distance_sma200_pct=result.metrics.distance_sma200_pct,
            rs_rating=result.metrics.rs_rating,
            rs_percentile=result.metrics.rs_percentile,
            beta=result.metrics.beta,
            institutional_ownership_pct=result.metrics.institutional_ownership_pct,
            next_earnings_calendar_days=result.metrics.next_earnings_calendar_days,
            next_earnings_trading_days=result.metrics.next_earnings_trading_days,
        ),
        fundamentals=(
            StockFundamentalsItem(
                ticker=str(fundamentals.get("ticker") or result.ticker),
                as_of=str(fundamentals.get("as_of") or result.as_of),
                source=str(fundamentals.get("source") or ""),
                fiscal_period=str(fundamentals.get("fiscal_period") or ""),
                quarterly_eps_growth_pct=fundamentals.get("quarterly_eps_growth_pct"),
                annual_eps_growth_pct=fundamentals.get("annual_eps_growth_pct"),
                quarterly_revenue_growth_pct=fundamentals.get("quarterly_revenue_growth_pct"),
                annual_revenue_growth_pct=fundamentals.get("annual_revenue_growth_pct"),
                roe_pct=fundamentals.get("roe_pct"),
                profit_margin_pct=fundamentals.get("profit_margin_pct"),
                trailing_eps=fundamentals.get("trailing_eps"),
                quarterly_eps_accelerating=fundamentals.get("quarterly_eps_accelerating"),
                quarterly_revenue_accelerating=fundamentals.get("quarterly_revenue_accelerating"),
                institutional_holders=fundamentals.get("institutional_holders"),
                institutional_ownership_pct=fundamentals.get("institutional_ownership_pct"),
                next_earnings_date=fundamentals.get("next_earnings_date"),
                beta=fundamentals.get("beta"),
            )
            if fundamentals
            else None
        ),
        earnings=(
            StockEarningsWarning(
                next_earnings_date=result.earnings.next_earnings_date,
                calendar_days=result.earnings.calendar_days,
                trading_days=result.earnings.trading_days,
                tone=result.earnings.tone,
                message=result.earnings.message,
            )
            if result.earnings
            else None
        ),
        checks=[
            StockAssessmentCheck(
                category=check.category,
                label=check.label,
                passed=check.passed,
                detail=check.detail,
                severity=check.severity,
            )
            for check in result.checks
        ],
        chart_signals=[
            StockAssessmentSignal(
                category=signal.category,
                label=signal.label,
                detail=signal.detail,
            )
            for signal in result.chart_signals
        ],
        drivers=result.drivers,
        warnings=result.warnings,
    )


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_ranking_item(result: StockAssessmentResult, name: str) -> StockAssessmentRankingItem:
    return StockAssessmentRankingItem(
        ticker=result.ticker,
        name=name or result.ticker,
        as_of=result.as_of,
        verdict_label=result.verdict_label,
        verdict_tone=result.verdict_tone,
        overall_score=result.scores.overall,
        technical_score=result.scores.technical,
        fundamental_score=result.scores.fundamental,
        moving_average_score=result.scores.moving_averages,
        chart_behavior_score=result.scores.chart_behavior,
        rs_rating=result.metrics.rs_rating,
        dollar_volume_mio=result.metrics.dollar_volume_mio,
        atr_pct=result.metrics.atr_pct,
        warnings_count=len(result.warnings),
        top_warning=result.warnings[0] if result.warnings else "",
        top_driver=result.drivers[0] if result.drivers else "",
    )
