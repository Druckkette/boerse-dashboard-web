from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.data_sources.yfinance_client import FetchedLiveQuote, fetch_live_quotes_batch
from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.domain.sell.rules import compute_sell_health_score, evaluate_sell_decision, normalize_sell_setup_payload
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
    SellPostMortemNote,
    SellPostMortemNoteRequest,
    SellPostMortemNoteResponse,
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
from app.repositories import portfolio as portfolio_repository
from app.repositories import prices as prices_repository
from app.repositories import sell_state as sell_state_repository
from app.repositories.portfolio import PortfolioPositionRow, PortfolioRepositoryUnavailable
from app.repositories.prices import PriceRepositoryUnavailable
from app.services.fx import currency_to_usd, eur_to_usd, get_eur_usd_rate, yahoo_quote_currency
from app.services.data_quality import get_position_quality_by_ticker


_POSITION_MONITOR_REFERENCES = {"high_since_buy", "close_since_buy", "entry_price", "previous_close"}
_POSITION_MONITOR_REFERENCE_LABELS = {
    "high_since_buy": "Vom Hoch seit Kauf",
    "close_since_buy": "Vom Schlusskurs-Hoch seit Kauf",
    "entry_price": "Vom Einstand",
    "previous_close": "Vom Vortagesschluss",
}
MINIMUM_SELL_PRICE_BARS = 80


class SellPositionNotFoundError(LookupError):
    pass


class SellMarketDataUnavailableError(RuntimeError):
    pass


def get_sell_metrics_for_position(
    ticker: str,
    request: SellMetricsRequest | None = None,
) -> SellMetricsApiResponse:
    """Return sell metrics for an open position backed by cached market data."""
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
    snapshot_rows, generated_at, source_job_id = sell_state_repository.list_ranking_snapshot()
    if snapshot_rows:
        quality_by_ticker = get_position_quality_by_ticker()
        return SellRankingResponse(
            rows=[_with_data_quality(row, quality_by_ticker) for row in snapshot_rows],
            source="snapshot",
            generated_at=generated_at.isoformat() if generated_at else "",
            source_job_id=source_job_id,
            message="Vorberechneter Positionsmonitor-Snapshot aus Postgres.",
        )

    return _compute_sell_position_ranking_live()


def _compute_sell_position_ranking_live() -> SellRankingResponse:
    rows: list[SellPositionRankingItem] = []
    quality_by_ticker = get_position_quality_by_ticker()
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
        state = evaluation.next_recommendation_state
        rows.append(
            _with_data_quality(
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
                last_seen_date=state.last_seen_date,
                consecutive_days=state.consecutive_days,
                snoozed_until=state.snoozed_until,
                snoozed_pct=state.snoozed_pct,
                ),
                quality_by_ticker,
            )
        )
    rows.sort(
        key=lambda row: (
            {"Verkaufen": 0, "Beobachten": 1, "Halten": 2}.get(row.status, 3),
            -row.recommendation_pct,
            row.health_score,
        )
    )
    return SellRankingResponse(
        rows=rows,
        source="live",
        message="Live berechnet, weil noch kein Positionsmonitor-Snapshot vorhanden ist.",
    )


def _with_data_quality(
    row: SellPositionRankingItem,
    quality_by_ticker: dict[str, dict[str, str]],
) -> SellPositionRankingItem:
    quality = quality_by_ticker.get(row.ticker.upper())
    if quality is None:
        return row.model_copy(
            update={
                "data_quality_status": "limited",
                "data_quality_detail": "Für diese Position liegt keine Datenqualitätsprüfung vor.",
            }
        )
    return row.model_copy(
        update={
            "data_quality_status": quality["status"],
            "data_quality_detail": quality["detail"],
        }
    )


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
        post_mortem_notes=sell_state_repository.list_post_mortem_notes(clean_ticker),
        next_action=_next_action_text(evaluation),
    )


def update_manual_sell_inputs(ticker: str, manual: SellManualInput) -> ManualInputResponse:
    clean_ticker = _clean_ticker(ticker)
    stored = manual.model_copy(update={"ticker": clean_ticker, "sell_setup": normalize_sell_setup_payload(manual.sell_setup)})
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


def get_sell_post_mortem_notes(ticker: str) -> list[SellPostMortemNote]:
    return sell_state_repository.list_post_mortem_notes(_clean_ticker(ticker))


def upsert_sell_post_mortem_note(
    ticker: str,
    request: SellPostMortemNoteRequest,
) -> SellPostMortemNoteResponse:
    clean_ticker = _clean_ticker(ticker)
    note = SellPostMortemNote(
        ticker=clean_ticker,
        check_key=request.check_key,
        note=request.note,
        action=request.action,
        status=request.status,
    )
    stored = sell_state_repository.upsert_post_mortem_note(note)
    return SellPostMortemNoteResponse(
        note=stored,
        notes=sell_state_repository.list_post_mortem_notes(clean_ticker),
    )


def clear_sell_engine_state() -> None:
    """Test helper for the in-memory repository implementation."""
    sell_state_repository.clear_memory_sell_state()


def monitor_open_positions(
    tickers: list[str] | None = None,
    monitor_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all open positions using cached sell metrics and persist recommendation state."""

    settings = monitor_settings or {}
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
    ranking_items: list[SellPositionRankingItem] = []
    live_quotes = _position_monitor_live_quotes(portfolio_rows)
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
        quote = live_quotes.get(_clean_ticker(row.ticker))
        live_price = _position_monitor_live_price(quote)
        monitor_state = _monitor_state_from_metrics(
            row,
            metrics,
            settings,
            current_price_override=live_price,
            current_price_source=quote.source if quote and live_price is not None else "live_quote_unavailable",
            current_trade_date=quote.trade_date if quote and live_price is not None else None,
        )
        monitor_state["live_quote_at"] = quote.quote_at.isoformat() if quote and quote.quote_at else None
        monitor_state["live_quote_error"] = quote.error_message if quote else "Kein Yahoo-Live-Kurs empfangen."
        ranking_items.append(
            SellPositionRankingItem(
                ticker=row.ticker,
                name=row.name or row.ticker,
                pnl_pct=float(metrics.pnl_pct or 0.0),
                health_score=float(metrics.health.health_score),
                recommendation_pct=int(evaluation.recommendation_percent),
                status=_ranking_status(metrics.health.status, evaluation.recommendation_percent),
                reason=evaluation.explanation_short,
                pending_status=evaluation.pending_status,
                primary_signal=_primary_signal_label(evaluation),
                last_seen_date=evaluation.next_recommendation_state.last_seen_date,
                consecutive_days=evaluation.next_recommendation_state.consecutive_days,
                snoozed_until=evaluation.next_recommendation_state.snoozed_until,
                snoozed_pct=evaluation.next_recommendation_state.snoozed_pct,
            )
        )
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
                "monitor": monitor_state,
            }
        )

    snapshot_count = sell_state_repository.upsert_ranking_snapshot(
        ranking_items,
        source_job_id=str(settings.get("source_job_id") or ""),
        replace_all=not bool(allowed),
    )
    return {
        "ok": True,
        "records_seen": len(portfolio_rows),
        "records_written": len(items),
        "ranking_snapshot_written": snapshot_count,
        "items": items,
    }


def monitor_open_position_atr(
    tickers: list[str] | None = None,
    monitor_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the lightweight live ATR path without evaluating the full sell engine."""

    settings = monitor_settings or {}
    allowed = {_clean_ticker(ticker) for ticker in tickers or [] if _clean_ticker(ticker)}
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

    live_quotes = _position_monitor_live_quotes(portfolio_rows)
    items: list[dict[str, Any]] = []
    live_quotes_available = 0
    for row in portfolio_rows:
        quote = live_quotes.get(_clean_ticker(row.ticker))
        live_price = _position_monitor_live_price(quote)
        if live_price is not None:
            live_quotes_available += 1
        daily_frame = _price_frame_from_cache(row.ticker).rename(columns=lambda value: str(value).lower())
        monitor_state = _monitor_state_from_frame(
            row,
            daily_frame,
            settings,
            current_price_override=live_price,
            current_price_source=quote.source if quote and live_price is not None else "live_quote_unavailable",
            current_trade_date=quote.trade_date if quote and live_price is not None else None,
        )
        monitor_state["live_quote_at"] = quote.quote_at.isoformat() if quote and quote.quote_at else None
        monitor_state["live_quote_error"] = quote.error_message if quote else "Kein Yahoo-Live-Kurs empfangen."
        items.append(
            {
                "ticker": row.ticker,
                "name": row.name,
                "as_of": (
                    daily_frame.index[-1].date().isoformat()
                    if not daily_frame.empty and hasattr(daily_frame.index[-1], "date")
                    else None
                ),
                "monitor": monitor_state,
            }
        )

    return {
        "ok": True,
        "records_seen": len(portfolio_rows),
        "records_written": len(items),
        "live_quotes_requested": len(portfolio_rows),
        "live_quotes_available": live_quotes_available,
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


def _monitor_state_from_metrics(
    row: PortfolioPositionRow,
    metrics: SellMetricsApiResponse,
    settings: dict[str, Any],
    *,
    current_price_override: float | None = None,
    current_price_source: str = "live_quote_unavailable",
    current_trade_date: date | None = None,
) -> dict[str, Any]:
    daily_frame = metrics.raw_payload.ohlc_frames.get("daily_since_buy")
    return _monitor_state_from_frame(
        row,
        daily_frame,
        settings,
        current_price_override=current_price_override,
        current_price_source=current_price_source,
        current_trade_date=current_trade_date,
        fallback_atr=metrics.atr14,
    )


def _monitor_state_from_frame(
    row: PortfolioPositionRow,
    daily_frame: Any,
    settings: dict[str, Any],
    *,
    current_price_override: float | None,
    current_price_source: str,
    current_trade_date: date | None,
    fallback_atr: float | None = None,
) -> dict[str, Any]:
    atr_period = int(_finite_float(settings.get("position_monitor_atr_period"), 14) or 14)
    threshold_atr = float(_finite_float(settings.get("position_monitor_threshold_atr"), 1.5) or 1.5)
    lookback_days = int(_finite_float(settings.get("position_monitor_lookback_days"), 420) or 420)
    reference_mode = str(settings.get("position_monitor_reference") or "previous_close")
    if reference_mode not in _POSITION_MONITOR_REFERENCES:
        reference_mode = "previous_close"

    raw_current_price = _finite_float(current_price_override)
    raw_reference_price = _monitor_reference_price(
        daily_frame=daily_frame,
        row=row,
        current_price=raw_current_price,
        reference_mode=reference_mode,
        lookback_days=lookback_days,
        current_trade_date=current_trade_date,
    )
    raw_atr_value = _monitor_atr(daily_frame, atr_period) or fallback_atr
    quote_currency = yahoo_quote_currency(row.ticker)
    current_price = _monitor_value_usd(raw_current_price, quote_currency)
    reference_price = _monitor_value_usd(
        raw_reference_price,
        row.currency if reference_mode == "entry_price" else quote_currency,
    )
    atr_value = _monitor_value_usd(raw_atr_value, quote_currency)
    distance_atr = None
    threshold_crossed = False
    if reference_price is not None and atr_value is not None and atr_value > 0 and current_price is not None:
        distance_atr = (reference_price - current_price) / atr_value
        threshold_crossed = distance_atr >= threshold_atr

    return {
        "enabled": bool(settings.get("position_monitor_enabled", True)),
        "reference": reference_mode,
        "reference_label": _POSITION_MONITOR_REFERENCE_LABELS.get(reference_mode, reference_mode),
        "reference_price": _round_metric(reference_price),
        "current_price": _round_metric(current_price),
        "current_price_source": current_price_source,
        "value_currency": "USD",
        "atr_period": atr_period,
        "atr_value": _round_metric(atr_value),
        "threshold_atr": threshold_atr,
        "distance_atr": _round_metric(distance_atr),
        "threshold_crossed": threshold_crossed,
        "cooldown_hours": int(_finite_float(settings.get("position_monitor_cooldown_hours"), 18) or 18),
    }


def _position_monitor_live_quotes(rows: list[PortfolioPositionRow]) -> dict[str, FetchedLiveQuote]:
    symbols = [_clean_ticker(row.ticker) for row in rows if _clean_ticker(row.ticker)]
    if not symbols:
        return {}
    try:
        return fetch_live_quotes_batch(symbols)
    except Exception:
        return {}


def _position_monitor_live_price(quote: FetchedLiveQuote | None) -> float | None:
    if quote is None:
        return None
    return _finite_float(quote.price)


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
                theme=_strategy_theme(key),
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
        emergency_features=raw.get("emergency_features") if isinstance(raw.get("emergency_features"), list) else [],
        offensive_features=raw.get("offensive_features") if isinstance(raw.get("offensive_features"), list) else [],
        defensive_features=raw.get("defensive_features") if isinstance(raw.get("defensive_features"), list) else [],
        strategy=raw.get("strategy") if isinstance(raw.get("strategy"), dict) else {},
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
    raise SellPositionNotFoundError(
        f"{clean_ticker} ist keine offene Portfolioposition. Der Verkaufsmonitor bewertet keine Testpositionen."
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
    return []


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
    buy_date = row.buy_date or date.today()
    buy_price, current_price, currency = _portfolio_row_prices_for_sell(row)
    return SellMetricsRequest(
        ticker=row.ticker,
        buy_date=buy_date,
        buy_price=buy_price,
        shares=row.shares,
        current_price=current_price,
        benchmark_ticker="SPY",
        currency=currency,
        pivot_date=buy_date,
        scenario=None,
    )


def _portfolio_row_prices_for_sell(row: PortfolioPositionRow) -> tuple[float, float | None, str]:
    entry_price = _finite_float(row.entry_price) or row.entry_price
    current_price = _finite_float(row.current_price, entry_price)
    currency = row.currency or "USD"
    if "trade republic" in str(row.broker or "").lower() and str(row.currency or "").upper() == "EUR":
        fx_rate = get_eur_usd_rate()
        entry_price = float(eur_to_usd(entry_price, rate=fx_rate) or entry_price)
        if row.current_price_source == "price_cache":
            converted_price = currency_to_usd(
                current_price,
                yahoo_quote_currency(row.ticker),
            )
            current_price = float(converted_price if converted_price is not None else entry_price)
        else:
            current_price = float(eur_to_usd(current_price, rate=fx_rate) or current_price)
        currency = "USD"
    return entry_price, current_price, currency


def _position_context(ticker: str) -> dict[str, Any]:
    clean_ticker = _clean_ticker(ticker)
    return {
        "name": clean_ticker,
        "market_environment": "Unsicher",
        "industry_group_status": "Neutral",
    }


def _build_metrics_payload(request: SellMetricsRequest) -> dict[str, Any]:
    price_frame = _price_frame_from_cache(request.ticker)
    if len(price_frame) < MINIMUM_SELL_PRICE_BARS:
        raise SellMarketDataUnavailableError(
            f"{request.ticker}: nur {len(price_frame)} Kurszeilen im Price Cache; "
            f"mindestens {MINIMUM_SELL_PRICE_BARS} werden für den Verkaufsmonitor benötigt."
        )

    benchmark_frame = _price_frame_from_cache(request.benchmark_ticker)
    if len(benchmark_frame) < MINIMUM_SELL_PRICE_BARS:
        raise SellMarketDataUnavailableError(
            f"{request.benchmark_ticker}: nur {len(benchmark_frame)} Benchmark-Zeilen im Price Cache; "
            f"mindestens {MINIMUM_SELL_PRICE_BARS} werden für den Verkaufsmonitor benötigt."
        )

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
        payload["metrics"]["price_data_source"] = "database"
        payload["metrics"]["benchmark_data_source"] = "database"
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


def _manual_for_payload(ticker: str, payload: dict[str, Any]) -> SellManualInput:
    return _resolve_manual(ticker, payload, None)


def _resolve_manual(
    ticker: str,
    payload: dict[str, Any],
    request_manual: SellManualInput | None,
) -> SellManualInput:
    clean_ticker = _clean_ticker(ticker)
    if request_manual is not None:
        return request_manual.model_copy(
            update={"ticker": clean_ticker, "sell_setup": normalize_sell_setup_payload(request_manual.sell_setup)}
        )
    stored_manual = sell_state_repository.get_manual_input(clean_ticker)
    if stored_manual is not None:
        return stored_manual.model_copy(update={"sell_setup": normalize_sell_setup_payload(stored_manual.sell_setup)})
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
    return "unbekannt"


def _monitor_reference_price(
    *,
    daily_frame: Any,
    row: PortfolioPositionRow,
    current_price: float | None,
    reference_mode: str,
    lookback_days: int,
    current_trade_date: date | None = None,
) -> float | None:
    if reference_mode == "entry_price":
        return _finite_float(row.entry_price, current_price)

    frame = _tail_ohlc_frame(daily_frame, lookback_days)
    if frame.empty:
        return _finite_float(current_price, row.entry_price)

    if reference_mode == "previous_close":
        if "close" not in frame:
            return _finite_float(current_price, row.entry_price)
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if current_trade_date is not None:
            closes_before_trade = closes[
                [pd.Timestamp(index).date() < current_trade_date for index in closes.index]
            ]
            if not closes_before_trade.empty:
                return _finite_float(closes_before_trade.iloc[-1], row.entry_price)
        if len(closes) >= 2:
            return _finite_float(closes.iloc[-2], current_price)
        return _finite_float(row.entry_price, current_price)

    if row.buy_date is not None:
        frame = frame[
            [pd.Timestamp(index).date() >= row.buy_date for index in frame.index]
        ]
        if frame.empty:
            return _finite_float(current_price, row.entry_price)

    column = "close" if reference_mode == "close_since_buy" else "high"
    if column not in frame:
        return _finite_float(current_price, row.entry_price)

    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return _finite_float(current_price, row.entry_price)
    return _finite_float(values.max(), current_price)


def _monitor_value_usd(value: float | None, currency: str) -> float | None:
    parsed = _finite_float(value)
    if parsed is None:
        return None
    return _finite_float(currency_to_usd(parsed, currency))


def _monitor_atr(daily_frame: Any, period: int) -> float | None:
    frame = _tail_ohlc_frame(daily_frame, max(period * 3, period + 2))
    if frame.empty or len(frame) < max(2, period):
        return None
    required = {"high", "low", "close"}
    if not required.issubset(set(frame.columns)):
        return None

    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(period).mean().dropna()
    if atr.empty:
        return None
    return _finite_float(atr.iloc[-1])


def _tail_ohlc_frame(frame: Any, lookback_days: int) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    cleaned = frame.copy()
    if not isinstance(cleaned.index, pd.DatetimeIndex):
        cleaned.index = pd.to_datetime(cleaned.index, errors="coerce")
        cleaned = cleaned[cleaned.index.notna()]
    cleaned = cleaned.sort_index()
    if lookback_days > 0:
        cleaned = cleaned.tail(lookback_days)
    return cleaned


def _strategy_tone(signals: list[SellSignal]) -> str:
    if any(signal.severity == "killer" for signal in signals):
        return "bad"
    if any(signal.severity in {"tranche", "warning"} for signal in signals):
        return "warning"
    if signals:
        return "neutral"
    return "good"


def _strategy_label(strategy_key: str) -> str:
    labels = {
        "custom": "Benutzerdefinierte Verkaufsstrategie",
        "rs_line": "RS-Linie mit 21/50-Durchschnitt",
        "ema21_risk_averse": "21-EMA-Bruch risikoavers",
        "ema21_offensive": "21-EMA-Bruch offensiv",
        "peak_drawdown": "Starker Rückgang vom 20-Tage-Hoch",
        "buy_day_low": "Unterschreitung des Kauftags",
        "ma_breaks": "Bruch gleitender Durchschnitte",
        "nothalt": "Nothalt",
    }
    if strategy_key in labels:
        return labels[strategy_key]
    clean = strategy_key.replace("lm_", "Live ").replace("_", " ").strip()
    return clean[:1].upper() + clean[1:] if clean else "Sonstige Strategie"


def _strategy_theme(strategy_key: str) -> str:
    if strategy_key in {"nothalt", "emergency_loss_limit"}:
        return "Nothalt"
    if strategy_key.startswith("defensive") or strategy_key in {"buy_day_low", "ma_breaks"}:
        return "Defensives Verkaufen"
    if strategy_key.startswith("offensive") or strategy_key in {"ema21_risk_averse", "ema21_offensive", "peak_drawdown"}:
        return "Offensives Verkaufen"
    if strategy_key == "rs_line":
        return "Relative Stärke"
    if strategy_key == "custom":
        return "Benutzerdefiniert"
    return "sonstige"


def _strategy_description(strategy_key: str) -> str:
    descriptions = {
        "custom": "Nutzt die pro Aktie konfigurierten Merkmale und Tranche-Prozente. Ohne Setup gelten robuste Defaults.",
        "rs_line": "Teilverkauf in drei Stufen, wenn die Relative-Stärke-Linie ihre 21- und 50-Tage-Linien verliert.",
        "ema21_risk_averse": "Frühe Tranchen bei erstem Bruch der 21-EMA, schwachem Folgetag und fortgesetztem Bruch.",
        "ema21_offensive": "Geduldiger: erste Tranche erst nach drei Schlüssen unter der 21-EMA.",
        "peak_drawdown": "Sichert Gewinner über Rückgangsstufen vom 20-Tage-Hoch und Trendbrüche.",
        "buy_day_low": "Überwacht das Tief des Kauftags und das Tief des Vortags vor dem Kauf.",
        "ma_breaks": "Erste Tranche nach bestätigtem 50-SMA-Bruch, finale Tranche beim 200-SMA-Bruch.",
    }
    return descriptions.get(strategy_key, "Live-Monitor- oder Watch-Signal aus der Sell-Engine.")


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
