from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

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
    StockAssessmentCompareItem,
    StockAssessmentCompareResponse,
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


def get_stock_assessment_compare(*, tickers: str, limit: int = 12) -> StockAssessmentCompareResponse:
    requested = _parse_compare_tickers(tickers, limit=limit)
    if len(requested) < 2:
        raise ValueError("Bitte mindestens zwei Ticker für den Aktienvergleich angeben.")

    items: list[StockAssessmentCompareItem] = []
    for ticker in requested:
        result, rs_row, rs_context = _build_assessment_result(ticker)
        items.append(_to_compare_item(result, name=rs_row.name if rs_row else ticker, rs_context=rs_context))

    items.sort(key=lambda item: (item.overall_score, item.technical_score, item.rs_rating or 0, item.ticker), reverse=True)
    ranked = [item.model_copy(update={"rank": index + 1}) for index, item in enumerate(items)]
    missing = [item.ticker for item in ranked if item.source == "missing"]
    database_count = len(ranked) - len(missing)
    source = "database" if database_count == len(ranked) else "partial" if database_count > 0 else "missing"
    as_of = ranked[0].as_of if ranked else date.today().isoformat()
    return StockAssessmentCompareResponse(
        as_of=as_of,
        source=source,
        requested_tickers=requested,
        missing_tickers=missing,
        rows=ranked,
    )


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
    eps_quarter_history = _coerce_eps_quarter_history(request.eps_quarter_history)
    latest_eps_growth = _latest_eps_growth(eps_quarter_history)
    row = fundamentals_repository.upsert_fundamentals(
        FundamentalSnapshotWrite(
            ticker=clean,
            as_of=as_of,
            source=request.source.strip() or "manual",
            fiscal_period=request.fiscal_period.strip(),
            quarterly_eps_growth_pct=(
                latest_eps_growth
                if latest_eps_growth is not None
                else request.quarterly_eps_growth_pct
            ),
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
            metadata_json={"entered_via": "web", "eps_quarter_history": eps_quarter_history},
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


def _build_assessment_result(ticker: str) -> tuple[StockAssessmentResult, RsRatingRow | None, dict]:
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

    rs_context = _rs_context(rs_row)
    result = compute_stock_assessment(
        clean,
        bars,
        rs_context=rs_context,
        fundamentals_context=_fundamentals_context(_safe_latest_fundamentals(clean)),
        institutional_context=_institutional_context(_safe_latest_13f(clean)),
    )
    return result, rs_row, rs_context


def _fundamentals_context(row: FundamentalSnapshotRow | None) -> dict:
    if row is None:
        return {}
    eps_quarter_history = _eps_history_from_metadata(row.metadata_json)
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
        "eps_quarter_history": eps_quarter_history,
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
    eps_quarter_history = _eps_history_from_metadata(row.metadata_json)
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
        eps_quarter_history=eps_quarter_history,
    )


def _eps_history_from_metadata(metadata: dict | None) -> list[dict[str, Any]]:
    raw = dict(metadata or {})
    candidates = [
        raw.get("eps_quarter_history"),
        (raw.get("enrichment") or {}).get("eps_quarter_history") if isinstance(raw.get("enrichment"), dict) else None,
        (raw.get("enrichment") or {}).get("eps_growth") if isinstance(raw.get("enrichment"), dict) else None,
        raw.get("eps_growth"),
    ]
    for candidate in candidates:
        history = _coerce_eps_quarter_history(candidate)
        if history:
            return history
    return []


def _coerce_eps_quarter_history(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    entries = value
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for item in entries:
        if hasattr(item, "model_dump"):
            raw = item.model_dump()
        elif isinstance(item, dict):
            raw = item
        else:
            continue
        fiscal_period = str(raw.get("fiscal_period") or raw.get("label") or raw.get("period") or "").strip()
        current = _float_or_none(raw.get("eps_current_quarter", raw.get("current")))
        previous = _float_or_none(raw.get("eps_same_quarter_last_year", raw.get("previous")))
        growth = _computed_eps_growth(current, previous)
        if growth is None and current is None and previous is None:
            growth = _float_or_none(raw.get("eps_growth_yoy_pct", raw.get("growth_pct")))
        out.append(
            {
                "fiscal_period": fiscal_period,
                "eps_current_quarter": current,
                "eps_same_quarter_last_year": previous,
                "eps_growth_yoy_pct": growth,
                "flag": raw.get("flag"),
            }
        )
    return out[:3]


def _latest_eps_growth(history: list[dict[str, Any]]) -> float | None:
    for item in history:
        value = _float_or_none(item.get("eps_growth_yoy_pct"))
        if value is not None:
            return value
    return None


def _computed_eps_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 1)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


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
                eps_quarter_history=fundamentals.get("eps_quarter_history") or [],
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


def _to_compare_item(result: StockAssessmentResult, *, name: str, rs_context: dict) -> StockAssessmentCompareItem:
    fundamental_checks = [check for check in result.checks if check.category == "fundamental"]
    technical_checks = [check for check in result.checks if check.category in {"technical", "trend", "risk"}]
    fundamental_counts = _check_counts(fundamental_checks)
    technical_counts = _check_counts(technical_checks)
    chart_counts = {
        "positive": sum(1 for signal in result.chart_signals if signal.category == "positive"),
        "negative": sum(1 for signal in result.chart_signals if signal.category == "negative"),
        "neutral": sum(1 for signal in result.chart_signals if signal.category == "neutral"),
    }

    return StockAssessmentCompareItem(
        rank=0,
        ticker=result.ticker,
        name=name or result.ticker,
        as_of=result.as_of,
        source=result.source,
        data_status=result.data_status,
        verdict_label=result.verdict_label,
        verdict_tone=result.verdict_tone,
        overall_score=result.scores.overall,
        technical_score=result.scores.technical,
        fundamental_score=result.scores.fundamental,
        moving_average_score=result.scores.moving_averages,
        chart_behavior_score=result.scores.chart_behavior,
        price=result.metrics.last_close,
        perf_1m_pct=_safe_number(rs_context.get("ret_1m_pct")),
        perf_3m_pct=_safe_number(rs_context.get("ret_3m_pct")),
        perf_6m_pct=_safe_number(rs_context.get("ret_6m_pct")),
        drawdown_52w_pct=result.metrics.drawdown_52w_pct,
        atr_pct=result.metrics.atr_pct,
        beta=result.metrics.beta,
        rs_rating=result.metrics.rs_rating,
        above_sma10=_positive_distance(result.metrics.distance_sma10_pct),
        above_ema21=_positive_distance(result.metrics.distance_ema21_pct),
        above_sma50=_positive_distance(result.metrics.distance_sma50_pct),
        above_sma200=_positive_distance(result.metrics.distance_sma200_pct),
        ma_order=_check_passed(result.checks, "MA-Ordnung (21>50>200)"),
        fundamental_criteria_passed=sum(1 for check in fundamental_checks if check.passed),
        fundamental_criteria_total=len(fundamental_checks),
        fundamental_positive=fundamental_counts["positive"],
        fundamental_negative=fundamental_counts["negative"],
        fundamental_neutral=fundamental_counts["neutral"],
        technical_positive=technical_counts["positive"],
        technical_negative=technical_counts["negative"],
        technical_neutral=technical_counts["neutral"],
        chart_positive=chart_counts["positive"],
        chart_negative=chart_counts["negative"],
        chart_neutral=chart_counts["neutral"],
        top_driver=result.drivers[0] if result.drivers else "",
        top_warning=result.warnings[0] if result.warnings else "",
    )


def _parse_compare_tickers(value: str, *, limit: int) -> list[str]:
    normalized: list[str] = []
    for raw in value.replace(";", ",").split(","):
        clean = "".join(char for char in raw.strip().upper() if char.isalnum() or char in {".", "-"})
        if clean and clean not in normalized:
            normalized.append(clean)
        if len(normalized) >= limit:
            break
    return normalized


def _check_counts(checks: list[StockAssessmentCheck]) -> dict[str, int]:
    positive = sum(1 for check in checks if check.passed)
    negative = sum(1 for check in checks if not check.passed and check.severity in {"warning", "critical"})
    neutral = max(len(checks) - positive - negative, 0)
    return {"positive": positive, "negative": negative, "neutral": neutral}


def _check_passed(checks: list[StockAssessmentCheck], label: str) -> bool | None:
    for check in checks:
        if check.label == label:
            return check.passed
    return None


def _positive_distance(value: float | None) -> bool | None:
    if value is None:
        return None
    return value > 0


def _safe_number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
