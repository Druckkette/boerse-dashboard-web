from __future__ import annotations

from copy import deepcopy
from datetime import date
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.domain.sell.rules import compute_sell_health_score, evaluate_sell_decision
from app.domain.sell.schemas import (
    ManualInputResponse,
    SellDiagnosticsResponse,
    SellEvaluationRequest,
    SellEvaluationResponse,
    SellHealthScore,
    SellLiveMonitorMetric,
    SellManualInput,
    SellMetricsApiResponse,
    SellMetricsPayload,
    SellMetricsRequest,
    SellPostMortemCheck,
    SellPositionRankingItem,
    SellRankingResponse,
    SellRecommendationState,
    SellSignal,
    SellStrategyDiagnostic,
    SnoozeRequest,
    SnoozeResponse,
    TrancheLogEntry,
    TrancheLogResponse,
    default_snoozed_until,
)
from app.domain.sell.strategies import STRATEGIE_INFO, STRATEGY_THEMES
from app.repositories import portfolio as portfolio_repository
from app.repositories import prices as prices_repository
from app.repositories import sell_state as sell_state_repository
from app.repositories.portfolio import PortfolioPositionRow, PortfolioRepositoryUnavailable
from app.repositories.prices import PriceRepositoryUnavailable


_SYNTHETIC_END_DATE = date(2026, 6, 5)
_SYNTHETIC_PERIODS = 280

_POSITION_CATALOG: dict[str, dict[str, Any]] = {
    "NVDA": {
        "name": "NVIDIA",
        "buy_price": 100.0,
        "shares": 12.0,
        "scenario": "profit",
        "market_environment": "Bullisch",
        "industry_group_status": "Stark",
    },
    "PLTR": {
        "name": "Palantir",
        "buy_price": 70.0,
        "shares": 20.0,
        "scenario": "losing",
        "market_environment": "Unsicher",
        "industry_group_status": "Neutral",
    },
    "EMAB": {
        "name": "EMA21 Break Setup",
        "buy_price": 100.0,
        "shares": 10.0,
        "scenario": "ema21_break",
        "market_environment": "Unsicher",
        "industry_group_status": "Neutral",
    },
    "CLMX": {
        "name": "Climax Winner",
        "buy_price": 80.0,
        "shares": 8.0,
        "scenario": "climax",
        "market_environment": "Bullisch",
        "industry_group_status": "Neutral",
    },
}

def get_sell_metrics_for_position(
    ticker: str,
    request: SellMetricsRequest | None = None,
) -> SellMetricsApiResponse:
    """Return sell metrics for one position.

    Current implementation uses deterministic fixture-like OHLC data. The function boundary is
    intentionally repository-friendly so a later price cache can replace the data source.
    """
    clean_ticker = _clean_ticker(ticker)
    payload = _build_metrics_payload(request or _default_metrics_request(clean_ticker))
    manual = _manual_for_payload(clean_ticker, payload)
    health = _health_from_payload(payload, manual)
    metrics = _payload_metrics(payload)

    return SellMetricsApiResponse(
        ticker=clean_ticker,
        as_of=str(payload.get("as_of") or ""),
        current_price=_round_metric(metrics.get("current_price")),
        pnl_pct=_round_metric(metrics.get("pnl_pct")),
        ema21=_round_metric(metrics.get("ema21")),
        sma50=_round_metric(metrics.get("sma50")),
        sma200=_round_metric(metrics.get("sma200")),
        atr14=_round_metric(metrics.get("atr14")),
        days_under_ema21=int(metrics.get("days_under_ema21") or 0),
        distribution_days_25=int(metrics.get("distribution_days_25") or 0),
        rs_trend=_api_rs_trend(health.rs_trend),
        health=health,
        manual_defaults=_json_safe(payload.get("manual_defaults", {})),
        auto_checkboxes=_json_safe(payload.get("auto_checkboxes", {})),
        raw_payload=_metrics_payload_schema(payload),
    )


def evaluate_position_sell_decision(
    ticker: str,
    request: SellEvaluationRequest | None = None,
) -> SellEvaluationResponse:
    response = _evaluate_position_sell_decision(ticker, request, persist_state=True)
    return response


def get_sell_position_ranking() -> SellRankingResponse:
    rows: list[SellPositionRankingItem] = []
    for context in _ranking_contexts():
        ticker = str(context["ticker"])
        metrics_request = context.get("metrics_request")
        metrics_response = get_sell_metrics_for_position(
            ticker,
            metrics_request if isinstance(metrics_request, SellMetricsRequest) else None,
        )
        evaluation = _evaluate_position_sell_decision(
            ticker,
            None,
            persist_state=False,
            metrics_request=metrics_request if isinstance(metrics_request, SellMetricsRequest) else None,
        )
        primary_signal = _primary_signal_label(evaluation)
        rows.append(
            SellPositionRankingItem(
                ticker=ticker,
                name=str(context["name"]),
                pnl_pct=float(metrics_response.pnl_pct or 0.0),
                health_score=float(metrics_response.health.health_score),
                recommendation_pct=int(evaluation.recommendation_percent),
                status=_ranking_status(metrics_response.health.status, evaluation.recommendation_percent),
                reason=evaluation.explanation_short,
                pending_status=evaluation.pending_status,
                primary_signal=primary_signal,
            )
        )
    rows.sort(
        key=lambda row: (
            {"Verkaufen": 0, "Beobachten": 1, "Halten": 2}.get(row.status, 3),
            -row.recommendation_pct,
            row.health_score,
        )
    )
    return SellRankingResponse(rows=rows)


def get_sell_diagnostics_for_position(ticker: str) -> SellDiagnosticsResponse:
    clean_ticker = _clean_ticker(ticker)
    metrics = get_sell_metrics_for_position(clean_ticker)
    evaluation = _evaluate_position_sell_decision(clean_ticker, None, persist_state=False)
    all_signals = [
        *evaluation.killer_signals,
        *evaluation.tranche_signals,
        *evaluation.warning_signals,
        *evaluation.watch_signals,
    ]
    return SellDiagnosticsResponse(
        ticker=clean_ticker,
        as_of=metrics.as_of,
        price_context=_live_monitor_metrics(metrics),
        strategy_hub=_strategy_hub(all_signals),
        post_mortem=_post_mortem_checks(metrics, evaluation),
        next_action=_next_action_text(evaluation),
    )


def update_manual_sell_inputs(ticker: str, manual: SellManualInput) -> ManualInputResponse:
    clean_ticker = _clean_ticker(ticker)
    stored = manual.model_copy(update={"ticker": clean_ticker})
    stored = sell_state_repository.upsert_manual_input(stored)
    return ManualInputResponse(manual=stored)


def create_tranche_log_entry(ticker: str, entry: TrancheLogEntry) -> TrancheLogResponse:
    clean_ticker = _clean_ticker(ticker)
    stored = entry.model_copy(update={"ticker": clean_ticker, "source": entry.source or "api"})
    stored = sell_state_repository.create_tranche_log_entry(stored)
    return TrancheLogResponse(entry=stored, tranche_log=sell_state_repository.list_tranche_log(clean_ticker))


def snooze_sell_signal(ticker: str, request: SnoozeRequest) -> SnoozeResponse:
    clean_ticker = _clean_ticker(ticker)
    previous = sell_state_repository.get_recommendation_state(clean_ticker) or SellRecommendationState()
    state = previous.model_copy(
        update={
            "snoozed_until": default_snoozed_until(request.days),
            "snoozed_pct": request.snoozed_pct,
        }
    )
    sell_state_repository.upsert_recommendation_state(clean_ticker, state)
    return SnoozeResponse(state=state)


def clear_sell_engine_state() -> None:
    """Test helper for the in-memory repository implementation."""
    sell_state_repository.clear_memory_sell_state()


def monitor_open_positions(tickers: list[str] | None = None) -> dict[str, Any]:
    """Evaluate all open positions using cached sell metrics and persist recommendation state."""

    allowed = set(_clean_ticker(ticker) for ticker in tickers or [] if _clean_ticker(ticker))
    portfolio_rows = [
        row for row in _portfolio_positions()
        if not allowed or _clean_ticker(row.ticker) in allowed
    ]
    if not portfolio_rows:
        return {
            "ok": False,
            "skipped": True,
            "reason": "Keine offenen importierten Positionen gefunden.",
            "records_seen": 0,
            "records_written": 0,
            "items": [],
        }

    items: list[dict[str, Any]] = []
    for row in portfolio_rows:
        metrics_request = _metrics_request_from_portfolio_row(row)
        metrics = get_sell_metrics_for_position(row.ticker, metrics_request)
        evaluation = _evaluate_position_sell_decision(
            row.ticker,
            None,
            persist_state=True,
            metrics_request=metrics_request,
        )
        price_source = str(metrics.raw_payload.metrics.get("price_data_source") or "")
        atr_pct = None
        if metrics.atr14 is not None and metrics.current_price:
            atr_pct = metrics.atr14 / metrics.current_price * 100
        items.append(
            {
                "ticker": row.ticker,
                "name": row.name,
                "as_of": metrics.as_of,
                "price_data_source": price_source,
                "current_price": metrics.current_price,
                "pnl_pct": metrics.pnl_pct,
                "atr14": metrics.atr14,
                "atr_pct": _round_metric(atr_pct),
                "health_score": metrics.health.health_score,
                "status": metrics.health.status,
                "recommendation_percent": evaluation.recommendation_percent,
                "pending_status": evaluation.pending_status,
                "primary_signal": _primary_signal_label(evaluation),
            }
        )

    return {
        "ok": True,
        "records_seen": len(portfolio_rows),
        "records_written": len(items),
        "items": items,
    }


def _live_monitor_metrics(metrics: SellMetricsApiResponse) -> list[SellLiveMonitorMetric]:
    price_source = str(metrics.raw_payload.metrics.get("price_data_source") or "")
    atr_pct = metrics.atr14 / metrics.current_price * 100 if metrics.atr14 and metrics.current_price else None
    return [
        SellLiveMonitorMetric(
            key="price_source",
            label="Datenquelle",
            value=_data_source_label(price_source),
            detail="Price Cache bevorzugt, Fallback nur als Warnung.",
            tone="good" if price_source == "database" else "warning",
        ),
        SellLiveMonitorMetric(
            key="current_price",
            label="Letzter Kurs",
            value=_fmt_number(metrics.current_price),
            detail=f"Stand {metrics.as_of}",
        ),
        SellLiveMonitorMetric(
            key="pnl_pct",
            label="P&L",
            value=_fmt_pct(metrics.pnl_pct),
            detail="seit Einstieg",
            tone="good" if (metrics.pnl_pct or 0) >= 0 else "bad",
        ),
        SellLiveMonitorMetric(
            key="atr14",
            label="ATR14",
            value=_fmt_number(metrics.atr14),
            detail=f"{_fmt_pct(atr_pct)} vom Kurs",
            tone="warning" if atr_pct is not None and atr_pct >= 6 else "neutral",
        ),
        SellLiveMonitorMetric(
            key="ema21",
            label="21-EMA",
            value=_fmt_number(metrics.ema21),
            detail=f"{metrics.days_under_ema21} Tage darunter",
            tone="warning" if metrics.days_under_ema21 > 0 else "good",
        ),
        SellLiveMonitorMetric(
            key="sma50",
            label="50-SMA",
            value=_fmt_number(metrics.sma50),
            detail="mittelfristiger Trendfilter",
        ),
        SellLiveMonitorMetric(
            key="distribution_days",
            label="Distribution",
            value=str(metrics.distribution_days_25),
            detail="Tage in 25 Sessions",
            tone="warning" if metrics.distribution_days_25 >= 4 else "good",
        ),
        SellLiveMonitorMetric(
            key="rs_trend",
            label="RS Trend",
            value=metrics.rs_trend,
            detail="hoch / seitwärts / runter",
            tone="good" if metrics.rs_trend == "hoch" else "bad" if metrics.rs_trend == "runter" else "neutral",
        ),
    ]


def _strategy_hub(signals: list[SellSignal]) -> list[SellStrategyDiagnostic]:
    by_strategy: dict[str, list[SellSignal]] = {}
    for signal in signals:
        key = signal.strategy_key or signal.id or signal.severity
        by_strategy.setdefault(key, []).append(signal)

    diagnostics: list[SellStrategyDiagnostic] = []
    for key, items in by_strategy.items():
        active = [item for item in items if item.severity in {"killer", "tranche"}]
        watch = [item for item in items if item.severity in {"warning", "watch"}]
        diagnostics.append(
            SellStrategyDiagnostic(
                strategy_key=key,
                theme=STRATEGY_THEMES.get(key, "sonstige"),
                label=_strategy_label(key),
                status="active" if active else "watch" if watch else "clear",
                tone=_strategy_tone(items),
                active_signal_count=len(active),
                watch_signal_count=len(watch),
                max_contribution_percent=max((item.contribution_percent for item in items), default=0),
                book_reference=_first_non_empty(item.book_reference for item in items),
                description=_strategy_description(key),
                signals=items,
            )
        )

    diagnostics.sort(
        key=lambda item: (
            {"bad": 0, "warning": 1, "neutral": 2, "good": 3}[item.tone],
            -item.max_contribution_percent,
            item.strategy_key,
        )
    )
    return diagnostics


def _post_mortem_checks(
    metrics: SellMetricsApiResponse,
    evaluation: SellEvaluationResponse,
) -> list[SellPostMortemCheck]:
    price_source = str(metrics.raw_payload.metrics.get("price_data_source") or "")
    pnl = float(metrics.pnl_pct or 0.0)
    return [
        SellPostMortemCheck(
            key="data_quality",
            label="Datenqualität",
            status="ok" if price_source == "database" else "review",
            tone="good" if price_source == "database" else "warning",
            evidence=f"Kursdatenquelle: {_data_source_label(price_source)}",
        ),
        SellPostMortemCheck(
            key="risk_budget",
            label="Verlustrisiko",
            status="fail" if pnl <= -7 else "ok" if pnl >= 0 else "review",
            tone="bad" if pnl <= -7 else "good" if pnl >= 0 else "warning",
            evidence=f"P&L {_fmt_pct(metrics.pnl_pct)}, Empfehlung {evaluation.sell_now_percent}%",
        ),
        SellPostMortemCheck(
            key="trend_filter",
            label="Trendfilter",
            status="fail" if metrics.days_under_ema21 >= 3 else "review" if metrics.days_under_ema21 > 0 else "ok",
            tone="bad" if metrics.days_under_ema21 >= 3 else "warning" if metrics.days_under_ema21 > 0 else "good",
            evidence=f"{metrics.days_under_ema21} Tage unter 21-EMA",
        ),
        SellPostMortemCheck(
            key="distribution",
            label="Distribution",
            status="review" if metrics.distribution_days_25 >= 4 else "ok",
            tone="warning" if metrics.distribution_days_25 >= 4 else "good",
            evidence=f"{metrics.distribution_days_25} Distributionstage in 25 Sessions",
        ),
        SellPostMortemCheck(
            key="execution_state",
            label="Ausführungsstand",
            status="review" if evaluation.sell_now_percent > 0 and evaluation.already_sold_percent == 0 else "ok",
            tone="warning" if evaluation.sell_now_percent > 0 and evaluation.already_sold_percent == 0 else "good",
            evidence=f"{evaluation.already_sold_percent:.0f}% bereits verkauft, Ziel {evaluation.target_total_sold_percent}%",
        ),
    ]


def _next_action_text(evaluation: SellEvaluationResponse) -> str:
    if evaluation.sell_now_percent > 0:
        return f"{evaluation.sell_now_percent}% Verkauf prüfen: {evaluation.explanation_short}"
    if evaluation.pending_status == "snoozed":
        return "Signal ist snoozed; nächster Check nach Ablauf des Snooze-Fensters."
    if evaluation.watch_signals or evaluation.warning_signals:
        return evaluation.explanation_short or "Watch-/Warnsignale weiter beobachten."
    return "Keine aktive Verkaufsaktion. Position weiter monitoren."


def _evaluate_position_sell_decision(
    ticker: str,
    request: SellEvaluationRequest | None,
    *,
    persist_state: bool,
    metrics_request: SellMetricsRequest | None = None,
) -> SellEvaluationResponse:
    clean_ticker = _clean_ticker(ticker)
    payload = _build_metrics_payload(metrics_request or _default_metrics_request(clean_ticker))
    manual = _resolve_manual(clean_ticker, payload, request.manual if request else None)
    tranche_log = (
        request.tranche_log
        if request and request.tranche_log is not None
        else sell_state_repository.list_tranche_log(clean_ticker)
    )
    recommendation_state = (
        request.recommendation_state
        if request and request.recommendation_state is not None
        else sell_state_repository.get_recommendation_state(clean_ticker)
    )

    raw = evaluate_sell_decision(
        payload,
        _manual_to_rule_dict(manual),
        _tranche_log_to_rule_dicts(tranche_log, clean_ticker),
        recommendation_state.model_dump(mode="json") if recommendation_state else None,
    )
    health = _health_from_payload(payload, manual)
    next_state = SellRecommendationState.model_validate(raw.get("next_recommendation_state") or {})

    response = SellEvaluationResponse(
        ticker=clean_ticker,
        recommendation_label=raw.get("recommendation_label", "HALTEN"),
        display_label=str(raw.get("display_label") or "HALTEN"),
        regime=str(raw.get("regime") or ""),
        sell_now_percent=int(raw.get("sell_now_percent") or 0),
        recommendation_percent=int(raw.get("recommendation_percent") or 0),
        target_total_sold_percent=int(raw.get("target_total_sold_percent") or 0),
        already_sold_percent=float(raw.get("already_sold_percent") or 0.0),
        remaining_after_sale_percent=float(raw.get("remaining_after_sale_percent") or 100.0),
        pending_status=raw.get("pending_status", "halten"),
        explanation_short=str(raw.get("explanation_short") or ""),
        stop_price=_round_metric(raw.get("stop_price")),
        next_tranche_trigger_price=_round_metric(raw.get("next_tranche_trigger_price")),
        full_exit_price=_round_metric(raw.get("full_exit_price")),
        add_again_condition=str(raw.get("add_again_condition") or ""),
        sell_mode=str(raw.get("sell_mode") or ""),
        sell_style=str(raw.get("sell_style") or ""),
        killer_signals=_signals_from_raw(raw.get("killer_signals"), "killer"),
        tranche_signals=_signals_from_raw(raw.get("tranche_signals"), "tranche"),
        warning_signals=_signals_from_raw(raw.get("warning_signals"), "warning"),
        watch_signals=_signals_from_raw(raw.get("watch_signals"), "watch"),
        book_references=_json_safe(raw.get("book_references") or {}),
        next_recommendation_state=next_state,
        health=health,
        manual=manual,
        tranche_log=list(tranche_log),
    )
    if persist_state:
        sell_state_repository.upsert_recommendation_state(clean_ticker, next_state)
    return response


def _default_metrics_request(ticker: str) -> SellMetricsRequest:
    clean_ticker = _clean_ticker(ticker)
    portfolio_row = _portfolio_position_context(clean_ticker)
    if portfolio_row is not None:
        return _metrics_request_from_portfolio_row(portfolio_row)
    context = _position_context(clean_ticker)
    dates = _price_dates()
    return SellMetricsRequest(
        ticker=clean_ticker,
        buy_date=dates[-170].date(),
        buy_price=float(context["buy_price"]),
        shares=float(context["shares"]),
        benchmark_ticker="SPY",
        currency="USD",
        pivot_date=dates[-170].date(),
        scenario=str(context["scenario"]),
    )


def _ranking_contexts() -> list[dict[str, Any]]:
    portfolio_rows = _portfolio_positions()
    if portfolio_rows:
        return [
            {
                "ticker": row.ticker,
                "name": row.name or row.ticker,
                "metrics_request": _metrics_request_from_portfolio_row(row),
            }
            for row in portfolio_rows
        ]
    return [
        {
            "ticker": ticker,
            "name": context["name"],
            "metrics_request": None,
        }
        for ticker, context in _POSITION_CATALOG.items()
    ]


def _portfolio_positions() -> list[PortfolioPositionRow]:
    try:
        return portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        return []


def _portfolio_position_context(ticker: str) -> PortfolioPositionRow | None:
    clean_ticker = _clean_ticker(ticker)
    for row in _portfolio_positions():
        if _clean_ticker(row.ticker) == clean_ticker:
            return row
    return None


def _metrics_request_from_portfolio_row(row: PortfolioPositionRow) -> SellMetricsRequest:
    dates = _price_dates()
    buy_date = row.buy_date or dates[-170].date()
    current_price = _finite_float(row.current_price, row.entry_price)
    return SellMetricsRequest(
        ticker=row.ticker,
        buy_date=buy_date,
        buy_price=row.entry_price,
        shares=row.shares,
        current_price=current_price,
        benchmark_ticker="SPY",
        currency=row.currency or "USD",
        pivot_date=buy_date,
        scenario=_scenario_for_portfolio_row(row),
    )


def _scenario_for_portfolio_row(row: PortfolioPositionRow) -> str:
    current_price = _finite_float(row.current_price, row.entry_price) or row.entry_price
    pnl_pct = (current_price / row.entry_price - 1) * 100 if row.entry_price else 0
    if pnl_pct <= -8:
        return "losing"
    if pnl_pct <= -3:
        return "ema21_break"
    if pnl_pct >= 70:
        return "climax"
    return "profit"


def _position_context(ticker: str) -> dict[str, Any]:
    clean_ticker = _clean_ticker(ticker)
    if clean_ticker in _POSITION_CATALOG:
        return _POSITION_CATALOG[clean_ticker]
    return {
        "name": clean_ticker,
        "buy_price": 100.0,
        "shares": 1.0,
        "scenario": "profit",
        "market_environment": "Unsicher",
        "industry_group_status": "Neutral",
    }


def _build_metrics_payload(request: SellMetricsRequest) -> dict[str, Any]:
    context = _position_context(request.ticker)
    is_catalog_default = (
        request.current_price is None
        and request.ticker in _POSITION_CATALOG
        and request.scenario == context["scenario"]
        and float(request.buy_price) == float(context["buy_price"])
        and float(request.shares) == float(context["shares"])
    )
    if is_catalog_default:
        return deepcopy(_cached_metrics_payload(request.ticker))

    price_frame = _price_frame_from_cache(request.ticker)
    price_data_source = "database"
    if len(price_frame) < 80:
        price_frame = _build_price_frame(request.scenario or "profit")
        price_frame = _scale_price_frame_to_last_close(price_frame, request.current_price)
        price_data_source = "synthetic_fallback"

    benchmark_frame = _price_frame_from_cache(request.benchmark_ticker)
    benchmark_data_source = "database"
    if len(benchmark_frame) < 80:
        benchmark_frame = _build_price_frame("benchmark")
        benchmark_data_source = "synthetic_fallback"

    payload = build_sell_decision_metrics_payload(
        ticker=request.ticker,
        buy_date=request.buy_date,
        buy_price=request.buy_price,
        shares=request.shares,
        price_frame=price_frame,
        benchmark_frame=benchmark_frame,
        benchmark_ticker=request.benchmark_ticker,
        currency=request.currency,
        pivot_date=request.pivot_date,
    )
    if isinstance(payload.get("metrics"), dict):
        payload["metrics"]["price_data_source"] = price_data_source
        payload["metrics"]["benchmark_data_source"] = benchmark_data_source
    return payload


def _price_frame_from_cache(ticker: str) -> pd.DataFrame:
    try:
        bars = prices_repository.list_price_bars(ticker)
    except PriceRepositoryUnavailable:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for bar in bars:
        close = _finite_float(bar.close)
        if close is None:
            continue
        open_price = _finite_float(bar.open, close) or close
        rows.append(
            {
                "Date": pd.Timestamp(bar.date),
                "Open": open_price,
                "High": _finite_float(bar.high, max(open_price, close)) or max(open_price, close),
                "Low": _finite_float(bar.low, min(open_price, close)) or min(open_price, close),
                "Close": close,
                "Volume": _finite_float(bar.volume, 1_000_000.0) or 1_000_000.0,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["Date"], keep="last").set_index("Date").sort_index()


def _scale_price_frame_to_last_close(frame: pd.DataFrame, current_price: float | None) -> pd.DataFrame:
    target = _finite_float(current_price)
    if frame.empty or target is None:
        return frame
    last_close = _finite_float(frame["Close"].iloc[-1] if "Close" in frame else None)
    if last_close is None or last_close <= 0:
        return frame
    scaled = frame.copy()
    factor = target / last_close
    for column in ("Open", "High", "Low", "Close"):
        if column in scaled:
            scaled[column] = pd.to_numeric(scaled[column], errors="coerce") * factor
    return scaled


@lru_cache(maxsize=64)
def _cached_metrics_payload(ticker: str) -> dict[str, Any]:
    request = _default_metrics_request(ticker)
    price_frame = _build_price_frame(request.scenario or "profit")
    benchmark_frame = _build_price_frame("benchmark")
    payload = build_sell_decision_metrics_payload(
        ticker=request.ticker,
        buy_date=request.buy_date,
        buy_price=request.buy_price,
        shares=request.shares,
        price_frame=price_frame,
        benchmark_frame=benchmark_frame,
        benchmark_ticker=request.benchmark_ticker,
        currency=request.currency,
        pivot_date=request.pivot_date,
    )
    if isinstance(payload.get("metrics"), dict):
        payload["metrics"]["price_data_source"] = "synthetic_fixture"
        payload["metrics"]["benchmark_data_source"] = "synthetic_fixture"
    return payload


def _build_price_frame(scenario: str) -> pd.DataFrame:
    dates = _price_dates()
    close = _close_curve(scenario, len(dates))
    idx = np.arange(len(dates), dtype=float)
    open_ = close * (1 + 0.004 * np.sin(idx / 4.0))
    high = np.maximum(open_, close) * (1.012 + 0.003 * np.cos(idx / 8.0))
    low = np.minimum(open_, close) * (0.988 - 0.002 * np.sin(idx / 6.0))
    volume = 1_000_000 * (1 + 0.12 * np.sin(idx / 9.0) + 0.04 * np.cos(idx / 3.0))

    if scenario == "losing":
        volume[-30:] *= np.linspace(1.2, 1.8, 30)
    elif scenario == "ema21_break":
        volume[-8:] *= np.linspace(1.1, 1.7, 8)
    elif scenario == "climax":
        volume[-6:] *= [1.2, 1.4, 2.2, 2.8, 2.0, 2.5]

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.maximum(volume, 100_000),
        },
        index=dates,
    )


def _close_curve(scenario: str, periods: int) -> np.ndarray:
    if scenario == "benchmark":
        curve = np.linspace(380, 430, periods)
        curve[-20:] = np.linspace(curve[-21], 432, 20)
        return curve
    if scenario == "losing":
        curve = np.linspace(86, 61, periods)
        curve[-15:] = np.linspace(curve[-16] * 0.98, 58.2, 15)
        return curve
    if scenario == "ema21_break":
        curve = np.concatenate(
            [
                np.linspace(82, 132, periods - 28),
                np.linspace(135, 123, 18),
                np.linspace(121, 118.5, 10),
            ]
        )
        return curve[:periods]
    if scenario == "climax":
        curve = np.linspace(72, 144, periods)
        curve[-8:] = [145, 149, 154, 162, 171, 166, 169, 174]
        return curve
    curve = np.linspace(82, 134, periods)
    curve[-18:] = np.linspace(curve[-19], 138, 18)
    return curve


def _price_dates() -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(_SYNTHETIC_END_DATE), periods=_SYNTHETIC_PERIODS)


def _manual_for_payload(ticker: str, payload: dict[str, Any]) -> SellManualInput:
    return _resolve_manual(ticker, payload, None)


def _resolve_manual(
    ticker: str,
    payload: dict[str, Any],
    request_manual: SellManualInput | None,
) -> SellManualInput:
    clean_ticker = _clean_ticker(ticker)
    if request_manual is not None:
        return request_manual.model_copy(update={"ticker": clean_ticker})
    stored_manual = sell_state_repository.get_manual_input(clean_ticker)
    if stored_manual is not None:
        return stored_manual
    context = _position_context(clean_ticker)
    defaults = payload.get("manual_defaults") if isinstance(payload, dict) else {}
    auto = payload.get("auto_checkboxes") if isinstance(payload, dict) else {}
    return SellManualInput(
        ticker=clean_ticker,
        pivot=_round_metric((defaults or {}).get("pivot")),
        low_day_1=_round_metric((defaults or {}).get("low_day_1")),
        low_day_0=_round_metric((defaults or {}).get("low_day_0")),
        market_environment=str(context["market_environment"]),
        industry_group_status=str(context["industry_group_status"]),
        strength_checkboxes=dict((auto or {}).get("strength_checkboxes") or {}),
        warning_checkboxes=dict((auto or {}).get("warning_checkboxes") or {}),
    )


def _health_from_payload(payload: dict[str, Any], manual: SellManualInput) -> SellHealthScore:
    raw = compute_sell_health_score(payload, _manual_to_rule_dict(manual))
    return SellHealthScore.model_validate(_json_safe(raw))


def _manual_to_rule_dict(manual: SellManualInput) -> dict[str, Any]:
    return manual.model_dump(mode="json")


def _tranche_log_to_rule_dicts(entries: list[TrancheLogEntry], ticker: str) -> list[dict[str, Any]]:
    clean_ticker = _clean_ticker(ticker)
    out: list[dict[str, Any]] = []
    for entry in entries:
        raw = entry.model_copy(update={"ticker": clean_ticker}).model_dump(mode="json")
        raw["tranche_percent"] = raw.get("pct", 0)
        out.append(raw)
    return out


def _signals_from_raw(raw_signals: Any, severity: str) -> list[SellSignal]:
    if not isinstance(raw_signals, list):
        return []
    return [_signal_from_raw(raw, severity) for raw in raw_signals if isinstance(raw, dict)]


def _signal_from_raw(raw: dict[str, Any], severity: str) -> SellSignal:
    return SellSignal(
        id=str(raw.get("id") or raw.get("name") or ""),
        label=str(raw.get("label") or raw.get("name") or ""),
        contribution_percent=int(raw.get("contribution_percent") or raw.get("tranche_pct") or 0),
        signal_date=str(raw.get("signal_date") or ""),
        event_note=str(raw.get("event_note") or raw.get("begruendung") or ""),
        sell_mode=str(raw.get("sell_mode") or ""),
        sell_style=str(raw.get("sell_style") or ""),
        strategy_key=str(raw.get("strategy_key") or ""),
        severity=severity,
        book_reference=str(raw.get("book_reference") or raw.get("buch_verweis") or ""),
    )


def _metrics_payload_schema(payload: dict[str, Any]) -> SellMetricsPayload:
    clean = {key: _json_safe(value) for key, value in payload.items() if key != "ohlc_frames"}
    clean["ohlc_frames"] = payload.get("ohlc_frames", {})
    return SellMetricsPayload.model_validate(clean)


def _payload_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") if isinstance(payload, dict) else {}
    return metrics if isinstance(metrics, dict) else {}


def _primary_signal_label(evaluation: SellEvaluationResponse) -> str:
    for group in (
        evaluation.killer_signals,
        evaluation.tranche_signals,
        evaluation.warning_signals,
        evaluation.watch_signals,
    ):
        if group:
            return group[0].label
    return "Keine aktiven Verkaufssignale"


def _ranking_status(health_status: str, recommendation_percent: int) -> str:
    if recommendation_percent >= 75:
        return "Verkaufen"
    if recommendation_percent > 0:
        return "Beobachten"
    return health_status


def _api_rs_trend(value: str) -> str:
    if value == "seitwärts":
        return "seitwaerts"
    if value in {"hoch", "runter", "seitwaerts"}:
        return value
    return "seitwaerts"


def _round_metric(value: Any, ndigits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return round(parsed, ndigits)


def _finite_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if np.isfinite(parsed) else default


def _fmt_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value:+.1f}%"


def _data_source_label(value: str) -> str:
    if value == "database":
        return "Price Cache"
    if value == "synthetic_fixture":
        return "Fixture"
    if value == "synthetic_fallback":
        return "Fallback"
    return "unbekannt"


def _strategy_tone(signals: list[SellSignal]) -> str:
    if any(signal.severity == "killer" for signal in signals):
        return "bad"
    if any(signal.severity in {"tranche", "warning"} for signal in signals):
        return "warning"
    if signals:
        return "neutral"
    return "good"


def _strategy_label(strategy_key: str) -> str:
    clean = strategy_key.replace("lm_", "Live ").replace("_", " ").strip()
    return clean[:1].upper() + clean[1:] if clean else "Sonstige Strategie"


def _strategy_description(strategy_key: str) -> str:
    info = STRATEGIE_INFO.get(strategy_key, "")
    if not info:
        return "Live-Monitor- oder Watch-Signal aus der Sell-Engine."
    return info.strip()[:220].rstrip()


def _first_non_empty(values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        parsed = float(value)
        return parsed if np.isfinite(parsed) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _clean_ticker(ticker: str) -> str:
    return str(ticker or "").upper().strip()
