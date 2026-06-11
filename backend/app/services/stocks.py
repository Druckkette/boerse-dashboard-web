from __future__ import annotations

from datetime import date, timedelta

from app.domain.stocks.assessment import StockAssessmentResult, compute_stock_assessment
from app.repositories import prices as price_repository
from app.repositories import relative_strength as rs_repository
from app.repositories.prices import PriceRepositoryUnavailable
from app.repositories.relative_strength import RelativeStrengthRepositoryUnavailable, RsRatingRow
from app.schemas import (
    StockAssessmentCheck,
    StockAssessmentMetrics,
    StockAssessmentResponse,
    StockAssessmentScores,
    StockAssessmentSignal,
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

    result = compute_stock_assessment(clean, bars, rs_context=_rs_context(rs_row))
    return _to_response(result)


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


def _to_response(result: StockAssessmentResult) -> StockAssessmentResponse:
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
