from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any

from app.domain.market.constants import (
    DEFAULT_MARKET_UNIVERSE_KEY,
    DEFAULT_MARKET_UNIVERSE_TICKERS,
    MARKET_CORE_PRICE_TICKERS,
    SECTOR_ETF_TICKERS,
)
from app.domain.market.volatility import VOLATILITY_TICKERS
from app.domain.sell.service import monitor_open_positions
from app.repositories import fundamentals as fundamentals_repository
from app.repositories import jobs as job_repository
from app.repositories import portfolio as portfolio_repository
from app.schemas import DataDiagnosticsResponse, FreshnessResponse, ServiceFreshness, UniverseStatusResponse
from app.services.freshness import get_freshness
from app.services.fundamentals import refresh_fundamentals_for_ticker
from app.services.market import refresh_market_breadth
from app.services.prices import PriceRange, PriceRefreshSymbol, refresh_price_cache_for_symbols
from app.services.relative_strength import DEFAULT_RS_BENCHMARK_TICKER, refresh_relative_strength_ratings
from app.services.sec13f import refresh_institutional_13f_from_sec
from app.services.settings import get_data_diagnostics, get_runtime_config_value
from app.services.universes import (
    get_universe_status,
    refresh_us_common_stock_universe,
    resolve_universe_price_symbols,
    resolve_universe_tickers,
)
from app.services.workspace import get_workspace_state
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled
from app.workers.tasks.refresh_fundamentals import resolve_fundamental_tickers


DEFAULT_PRICE_PROVIDER_TIMEOUT_SECONDS = 15
DEFAULT_PRICE_ACTION_MAX_SECONDS = 2 * 60 * 60
DEFAULT_FUNDAMENTAL_ACTION_MAX_SECONDS = 45 * 60
DEFAULT_FUNDAMENTAL_MAX_REFRESH_COUNT = 250
DEFAULT_FUNDAMENTAL_FRESHNESS_DAYS = 14


@dataclass(frozen=True)
class SmartRefreshAction:
    key: str
    job_type: str
    label: str
    reason: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "job_type": self.job_type,
            "label": self.label,
            "reason": self.reason,
            "payload": self.payload,
        }


@celery_app.task(bind=True, name="smart_refresh_market_data")
def smart_refresh_market_data(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "smart_refresh_market_data",
            payload,
            requested_by=str(payload.get("source") or "dashboard"),
        )

    result: dict[str, Any] = {
        "ok": False,
        "job_type": "smart_refresh_market_data",
        "mode": str(payload.get("mode") or "smart"),
        "actions": [],
        "skipped": [],
        "results": {},
    }

    job_repository.mark_running(job.job_id, step="Aktualität prüfen")
    try:
        raise_if_cancelled(job.job_id)
        diagnostics = get_data_diagnostics()
        freshness = get_freshness()
        universe_key = str(payload.get("universe") or DEFAULT_MARKET_UNIVERSE_KEY)
        universe_status = get_universe_status(universe_key)
        actions = build_smart_refresh_plan(
            diagnostics=diagnostics,
            freshness=freshness,
            universe_status=universe_status,
            payload=payload,
        )
        result["actions"] = [action.as_dict() for action in actions]
        result["freshness_before"] = _freshness_summary(freshness)
        result["diagnostics_before"] = {
            "open_positions_count": diagnostics.open_positions_count,
            "missing_price_count": diagnostics.missing_price_count,
            "stale_price_count": diagnostics.stale_price_count,
        }
        result["universe_before"] = {
            "source": universe_status.source,
            "member_count": universe_status.member_count,
            "updated_at": universe_status.updated_at.isoformat() if universe_status.updated_at else None,
        }

        if payload.get("dry_run"):
            result["ok"] = True
            job_repository.mark_done(job.job_id, result=result, message="Smart-Refresh-Plan wurde geprüft.")
            return result

        if not actions:
            result["ok"] = True
            result["skipped"].append({"reason": "Alle geprüften Marktdaten sind aktuell."})
            job_repository.mark_done(job.job_id, result=result, message="Alle geprüften Marktdaten sind aktuell.")
            return result

        total = max(1, len(actions))
        for index, action in enumerate(actions, start=1):
            raise_if_cancelled(job.job_id)
            progress = min(92, 8 + int((index - 1) / total * 82))
            job_repository.update_progress(
                job.job_id,
                progress=progress,
                step=action.label,
                message=action.reason,
                result=result,
            )
            action_result = _run_action(job.job_id, action, result=result, action_index=index, total_actions=total)
            result["results"][action.key] = action_result

        partial_actions = [
            key
            for key, value in result["results"].items()
            if isinstance(value, dict) and (value.get("partial") or value.get("stopped_due_to_timeout"))
        ]
        result["ok"] = True
        result["partial"] = bool(partial_actions)
        if partial_actions:
            result["partial_actions"] = partial_actions
        result["freshness_after"] = _freshness_summary(get_freshness())
        message = f"Smart Refresh abgeschlossen: {len(actions)} notwendige Aktion(en) ausgeführt."
        if partial_actions:
            message = (
                f"Smart Refresh teilweise abgeschlossen: {len(actions)} Aktion(en) geprüft; "
                f"{', '.join(partial_actions)} wird im nächsten Lauf fortgesetzt."
            )
        job_repository.mark_done(
            job.job_id,
            result=result,
            message=message,
        )
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def build_smart_refresh_plan(
    *,
    diagnostics: DataDiagnosticsResponse,
    freshness: FreshnessResponse,
    universe_status: UniverseStatusResponse,
    payload: dict | None = None,
) -> list[SmartRefreshAction]:
    payload = payload or {}
    universe_key = str(payload.get("universe") or DEFAULT_MARKET_UNIVERSE_KEY)
    limit_universe = _normalize_limit(payload.get("limit_universe") or 10000)
    benchmark_ticker = str(payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER).strip().upper()
    breadth_lookback_days = _normalize_days(payload.get("breadth_lookback_days") or payload.get("lookback_days") or 550)
    rs_lookback_days = _normalize_days(payload.get("rs_lookback_days") or 430)
    price_range = _normalize_range(payload.get("range") or "6m")
    initial_price_range = _normalize_range(payload.get("initial_range") or payload.get("price_range") or "2y")
    price_provider_timeout_seconds = _normalize_seconds(
        payload.get("price_provider_timeout_seconds") or payload.get("provider_timeout_seconds"),
        default=DEFAULT_PRICE_PROVIDER_TIMEOUT_SECONDS,
        min_value=3,
        max_value=120,
    )
    price_action_max_seconds = _normalize_seconds(
        payload.get("price_action_max_seconds") or payload.get("max_action_seconds"),
        default=DEFAULT_PRICE_ACTION_MAX_SECONDS,
        min_value=60,
        max_value=12 * 60 * 60,
    )
    price_batch_size = _normalize_batch_size(payload.get("price_batch_size") or payload.get("batch_size") or 50)
    price_overlap_days = _normalize_overlap_days(payload.get("price_overlap_days") or payload.get("overlap_days") or 1)
    include_position_monitor = bool(payload.get("include_position_monitor", True))
    include_fundamentals = bool(payload.get("include_fundamentals", True))
    force_fundamentals = _normalize_bool(payload.get("force_fundamentals"), default=False)
    include_sec13f = _normalize_bool(payload.get("include_sec13f"), default=True)
    force_sec13f = _normalize_bool(payload.get("force_sec13f"), default=False)
    force_market_refresh = _scheduled_or_forced(payload)
    incremental_prices = _normalize_bool(payload.get("incremental_prices"), default=True)
    incremental_fundamentals = _normalize_bool(payload.get("incremental_fundamentals"), default=True)
    fundamental_universe = str(
        payload.get("fundamental_universe") or ("all" if force_market_refresh else "tracked")
    ).strip().lower()
    fundamental_limit_default = limit_universe if fundamental_universe in {"all", "universe", universe_key} else 80
    fundamental_limit = _normalize_fundamental_limit(payload.get("fundamental_limit") or fundamental_limit_default)
    fundamental_max_refresh_count = _normalize_fundamental_max_refresh_count(
        payload.get("fundamental_max_refresh_count") or payload.get("fundamental_batch_limit")
    )
    fundamental_action_max_seconds = _normalize_seconds(
        payload.get("fundamental_action_max_seconds") or payload.get("max_action_seconds"),
        default=DEFAULT_FUNDAMENTAL_ACTION_MAX_SECONDS,
        min_value=60,
        max_value=6 * 60 * 60,
    )
    fundamental_freshness_days = _normalize_fundamental_freshness_days(
        payload.get("fundamental_freshness_days")
    )

    freshness_by_name = {item.name: item for item in freshness.services}
    price_freshness = freshness_by_name.get("prices")
    trend_benchmark_freshness = freshness_by_name.get("trend_benchmark")
    breadth_freshness = freshness_by_name.get("market_breadth")
    rs_freshness = freshness_by_name.get("relative_strength")
    sell_ranking_freshness = freshness_by_name.get("sell_ranking")
    fundamentals_freshness = freshness_by_name.get("fundamentals_tracked")
    sec13f_freshness = freshness_by_name.get("institutional_13f")
    issue_by_key = {issue.key: issue for issue in diagnostics.issues}

    actions: list[SmartRefreshAction] = []
    fundamental_action_payload: dict[str, Any] = {
        "mode": "tracked",
        "source": "smart_refresh",
        "fundamental_universe": fundamental_universe,
        "universe": universe_key if fundamental_universe in {"all", "universe"} else None,
        "fundamental_limit": fundamental_limit,
        "include_holders": True,
        "incremental": incremental_fundamentals,
        "fundamental_action_max_seconds": fundamental_action_max_seconds,
        "fundamental_max_refresh_count": fundamental_max_refresh_count,
        "fundamental_freshness_days": fundamental_freshness_days,
        "scheduled_window": payload.get("scheduled_window"),
    }
    incomplete_fundamental_tickers: list[str] = []
    if include_fundamentals and not (
        force_market_refresh
        or force_fundamentals
        or _is_missing(fundamentals_freshness)
        or _is_stale(fundamentals_freshness)
    ):
        incomplete_fundamental_tickers = _incomplete_fundamental_tickers(fundamental_action_payload)
    universe_needs_refresh = _universe_needs_refresh(universe_status)
    market_prices_need_refresh = (
        force_market_refresh
        or _is_missing(price_freshness)
        or _is_stale(price_freshness)
        or _is_missing(trend_benchmark_freshness)
        or _is_stale(trend_benchmark_freshness)
        or universe_needs_refresh
    )
    market_prices_were_missing = _is_missing(price_freshness) or universe_needs_refresh

    if universe_needs_refresh:
        actions.append(
            SmartRefreshAction(
                key="refresh_universe",
                job_type="refresh_universe",
                label="Aktienuniversum aktualisieren",
                reason="Das gespeicherte US-Aktienuniversum fehlt, ist zu klein oder älter als sieben Tage.",
                payload={"mode": "smart", "source": "smart_refresh"},
            )
        )

    if market_prices_need_refresh:
        reason = (
            "Geplanter Smart-Refresh: Kursdaten, Marktbreite und RS werden unabhängig vom Freshness-Fenster aktualisiert."
            if force_market_refresh
            else "Globale Kursdaten oder der Trend-Ampel-Benchmark fehlen oder sind veraltet; Marktbreite und RS brauchen aktuelle Kursdaten."
        )
        actions.append(
            SmartRefreshAction(
                key="refresh_market_prices",
                job_type="refresh_prices",
                label="Market-Price-Cache aktualisieren",
                reason=reason,
                payload={
                    "mode": "smart",
                    "source": "smart_refresh",
                    "range": initial_price_range if market_prices_were_missing else price_range,
                    "universe": universe_key,
                    "limit_universe": limit_universe,
                    "benchmark_ticker": benchmark_ticker,
                    "include_market_helpers": True,
                    "incremental": incremental_prices,
                    "price_provider_timeout_seconds": price_provider_timeout_seconds,
                    "price_action_max_seconds": price_action_max_seconds,
                    "price_batch_size": price_batch_size,
                    "price_overlap_days": price_overlap_days,
                },
            )
        )
    else:
        missing_price_issue = issue_by_key.get("missing_price_cache")
        stale_price_issue = issue_by_key.get("stale_price_cache")
        if missing_price_issue and missing_price_issue.tickers:
            actions.append(
                SmartRefreshAction(
                    key="refresh_missing_position_prices",
                    job_type="refresh_prices",
                    label="Fehlende Positionskurse laden",
                    reason=missing_price_issue.detail,
                    payload={
                        "mode": "smart",
                        "source": "smart_refresh",
                        "range": "1y",
                        "tickers": missing_price_issue.tickers,
                        "price_provider_timeout_seconds": price_provider_timeout_seconds,
                        "price_action_max_seconds": price_action_max_seconds,
                        "price_batch_size": price_batch_size,
                        "price_overlap_days": price_overlap_days,
                    },
                )
            )
        if stale_price_issue and stale_price_issue.tickers:
            actions.append(
                SmartRefreshAction(
                    key="refresh_stale_position_prices",
                    job_type="refresh_prices",
                    label="Veraltete Positionskurse aktualisieren",
                    reason=stale_price_issue.detail,
                    payload={
                        "mode": "smart",
                        "source": "smart_refresh",
                        "range": "6m",
                        "tickers": stale_price_issue.tickers,
                        "price_provider_timeout_seconds": price_provider_timeout_seconds,
                        "price_action_max_seconds": price_action_max_seconds,
                        "price_batch_size": price_batch_size,
                        "price_overlap_days": price_overlap_days,
                    },
                )
            )

    dependent_market_refresh = market_prices_need_refresh
    if dependent_market_refresh or _is_missing(breadth_freshness) or _is_stale(breadth_freshness):
        actions.append(
            SmartRefreshAction(
                key="refresh_breadth",
                job_type="refresh_breadth",
                label="Marktbreite berechnen",
                reason="Marktbreite fehlt, ist veraltet oder muss nach einem Kurs-Refresh neu berechnet werden.",
                payload={
                    "mode": "smart",
                    "source": "smart_refresh",
                    "universe": universe_key,
                    "limit_universe": limit_universe,
                    "lookback_days": breadth_lookback_days,
                },
            )
        )
    if dependent_market_refresh or _is_missing(rs_freshness) or _is_stale(rs_freshness):
        actions.append(
            SmartRefreshAction(
                key="refresh_relative_strength",
                job_type="refresh_relative_strength",
                label="Relative Stärke berechnen",
                reason="RS-Ratings fehlen, sind veraltet oder müssen nach einem Kurs-Refresh neu berechnet werden.",
                payload={
                    "mode": "smart",
                    "source": "smart_refresh",
                    "universe": universe_key,
                    "limit_universe": limit_universe,
                    "lookback_days": rs_lookback_days,
                    "benchmark_ticker": benchmark_ticker,
                },
            )
        )

    if include_fundamentals and (
        force_market_refresh
        or force_fundamentals
        or _is_missing(fundamentals_freshness)
        or _is_stale(fundamentals_freshness)
        or bool(incomplete_fundamental_tickers)
    ):
        reason = "Fundamental-Cache für offene Positionen, Watchlist und zuletzt geöffnete Aktien fehlt oder ist veraltet."
        action_payload = dict(fundamental_action_payload)
        if force_market_refresh:
            reason = "Geplanter Smart-Refresh: Fundamental-Historien werden geprüft und inkrementell aktualisiert."
        elif force_fundamentals:
            reason = "Manueller Smart-Refresh: Fundamental-Historien werden fuer das gewaehlte Universe inkrementell geprueft."
        elif incomplete_fundamental_tickers:
            sample = ", ".join(incomplete_fundamental_tickers[:8])
            suffix = "..." if len(incomplete_fundamental_tickers) > 8 else ""
            reason = (
                "Fundamental-Snapshots sind zeitlich frisch, aber EPS-/Umsatz-Historien sind unvollständig "
                f"({sample}{suffix})."
            )
            action_payload["tickers"] = incomplete_fundamental_tickers
            action_payload["repair_incomplete_histories"] = True
            action_payload["incomplete_tickers"] = incomplete_fundamental_tickers
        actions.append(
            SmartRefreshAction(
                key="refresh_fundamentals",
                job_type="refresh_fundamentals",
                label="Fundamentals aktualisieren",
                reason=reason,
                payload=action_payload,
            )
        )

    if include_sec13f and (force_sec13f or _is_missing(sec13f_freshness) or _is_stale(sec13f_freshness)):
        actions.append(
            SmartRefreshAction(
                key="refresh_sec13f",
                job_type="refresh_sec13f",
                label="13F/SEC-Trends aktualisieren",
                reason="Institutionelle 13F-Trends fehlen oder sind älter als das Quartals-Freshness-Fenster.",
                payload={
                    "mode": "incremental",
                    "source": "smart_refresh",
                    "universe": str(payload.get("sec13f_universe") or ("us_common_stocks" if force_market_refresh else "tracked")),
                    "limit_universe": _normalize_13f_limit(
                        payload.get("sec13f_limit_universe") or payload.get("sec13f_limit") or 500
                    ),
                    "dataset_count": _normalize_dataset_count(payload.get("sec13f_dataset_count") or 2),
                },
            )
        )

    prices_refreshed = any(action.job_type == "refresh_prices" for action in actions)
    if include_position_monitor and diagnostics.open_positions_count > 0:
        if prices_refreshed or _is_missing(sell_ranking_freshness) or _is_stale(sell_ranking_freshness):
            actions.append(
                SmartRefreshAction(
                    key="position_monitor",
                    job_type="position_atr_monitor",
                    label="Positionsmonitor prüfen",
                    reason="Offene Positionen sollen nach fehlenden/veralteten Kursen oder stale Sell-Ranking neu bewertet werden.",
                    payload={"mode": "smart", "source": "smart_refresh"},
                )
            )

    return actions


def _run_action(
    job_id: str,
    action: SmartRefreshAction,
    *,
    result: dict[str, Any],
    action_index: int,
    total_actions: int,
) -> dict[str, Any]:
    if action.job_type == "refresh_universe":
        return refresh_us_common_stock_universe()
    if action.job_type == "refresh_prices":
        return _refresh_prices(job_id, action.payload, result=result, action_index=action_index, total_actions=total_actions)
    if action.job_type == "refresh_breadth":
        tickers = resolve_universe_tickers(
            explicit_tickers=action.payload.get("tickers"),
            universe_key=action.payload.get("universe"),
            fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
            limit=int(action.payload.get("limit_universe") or 10000),
        )
        return refresh_market_breadth(
            tickers=tickers,
            universe=str(action.payload.get("universe") or DEFAULT_MARKET_UNIVERSE_KEY),
            lookback_days=int(action.payload.get("lookback_days") or 550),
        )
    if action.job_type == "refresh_relative_strength":
        tickers = resolve_universe_tickers(
            explicit_tickers=action.payload.get("tickers"),
            universe_key=action.payload.get("universe"),
            fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
            limit=int(action.payload.get("limit_universe") or 10000),
        )
        return refresh_relative_strength_ratings(
            tickers=tickers,
            benchmark_ticker=str(action.payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER),
            lookback_days=int(action.payload.get("lookback_days") or 430),
            source="computed",
        )
    if action.job_type == "position_atr_monitor":
        return monitor_open_positions(tickers=None)
    if action.job_type == "refresh_fundamentals":
        return _refresh_fundamentals(job_id, action.payload, result=result, action_index=action_index, total_actions=total_actions)
    if action.job_type == "refresh_sec13f":
        return _refresh_sec13f(job_id, action.payload, result=result, action_index=action_index, total_actions=total_actions)
    raise ValueError(f"Unsupported smart refresh action: {action.job_type}")


def _refresh_prices(
    job_id: str,
    payload: dict[str, Any],
    *,
    result: dict[str, Any],
    action_index: int,
    total_actions: int,
) -> dict[str, Any]:
    range_key = _normalize_range(payload.get("range") or "6m")
    provider_timeout_seconds = _normalize_seconds(
        payload.get("price_provider_timeout_seconds") or payload.get("provider_timeout_seconds"),
        default=DEFAULT_PRICE_PROVIDER_TIMEOUT_SECONDS,
        min_value=3,
        max_value=120,
    )
    max_action_seconds = _normalize_seconds(
        payload.get("price_action_max_seconds") or payload.get("max_action_seconds"),
        default=DEFAULT_PRICE_ACTION_MAX_SECONDS,
        min_value=60,
        max_value=12 * 60 * 60,
    )
    batch_size = _normalize_batch_size(payload.get("price_batch_size") or payload.get("batch_size") or 50)
    overlap_days = _normalize_overlap_days(payload.get("price_overlap_days") or payload.get("overlap_days") or 1)
    symbols = resolve_universe_price_symbols(
        explicit_tickers=payload.get("tickers"),
        universe_key=payload.get("universe"),
        fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
        limit=int(payload.get("limit_universe") or 10000),
    )
    if payload.get("include_market_helpers"):
        symbols = _merge_price_symbols(symbols, benchmark_ticker=str(payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER))

    price_result: dict[str, Any] = {
        "ok": False,
        "job_type": "refresh_prices",
        "range": range_key,
        "ticker_count": len(symbols),
        "success_count": 0,
        "failure_count": 0,
        "failed_tickers": [],
        "records_seen": 0,
        "records_written": 0,
        "provider_timeout_seconds": provider_timeout_seconds,
        "max_action_seconds": max_action_seconds,
        "batch_size": batch_size,
        "overlap_days": overlap_days,
        "batch_count": 0,
    }
    total_symbols = max(1, len(symbols))
    base_progress = 8 + int((action_index - 1) / max(1, total_actions) * 82)
    next_progress = 8 + int(action_index / max(1, total_actions) * 82)
    started_at = monotonic()
    for offset in range(0, len(symbols), batch_size):
        raise_if_cancelled(job_id)
        if _elapsed_seconds(started_at) >= max_action_seconds:
            skipped = total_symbols - offset
            price_result["skipped_count"] = int(price_result.get("skipped_count") or 0) + skipped
            price_result["stopped_due_to_timeout"] = True
            price_result["partial"] = price_result["success_count"] > 0
            price_result["ok"] = False
            price_result["timeout_message"] = (
                f"Price-Refresh nach {max_action_seconds // 60} Minuten gestoppt; "
                f"{skipped} Symbol(e) werden im nächsten Smart Refresh nachgezogen."
            )
            job_repository.update_progress(
                job_id,
                progress=min(92, base_progress + int(offset / total_symbols * max(1, next_progress - base_progress))),
                step="Smart Price Cache gestoppt",
                message=str(price_result["timeout_message"]),
                result={**result, "current_price_refresh": price_result},
            )
            if price_result["success_count"] == 0:
                raise RuntimeError(str(price_result["timeout_message"]))
            return price_result
        batch = symbols[offset : offset + batch_size]
        batch_end = offset + len(batch)
        progress = min(92, base_progress + int(batch_end / total_symbols * max(1, next_progress - base_progress)))
        job_repository.update_progress(
            job_id,
            progress=progress,
            step=f"Smart Price Batch {offset + 1}-{batch_end}/{total_symbols}",
            message=(
                f"{len(batch)} Yahoo-Symbol(e) gesammelt laden. "
                f"Timeout je Batch: {provider_timeout_seconds}s."
            ),
            result={**result, "current_price_refresh": price_result},
        )
        try:
            batch_items = refresh_price_cache_for_symbols(
                [
                    PriceRefreshSymbol(ticker=symbol.source_ticker, yahoo_symbol=symbol.yahoo_symbol)
                    for symbol in batch
                ],
                range_key=range_key,
                incremental=_normalize_bool(payload.get("incremental"), default=True),
                timeout=provider_timeout_seconds,
                batch_size=batch_size,
                overlap_days=overlap_days,
            )
        except Exception as exc:
            batch_items = [
                {
                    "ticker": symbol.source_ticker,
                    "yahoo_symbol": symbol.yahoo_symbol,
                    "ok": False,
                    "records_seen": 0,
                    "records_written": 0,
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "source": "yfinance",
                }
                for symbol in batch
            ]
        price_result["batch_count"] += 1
        for item in batch_items:
            if item.get("ok") is False:
                price_result["failure_count"] += 1
                if len(price_result["failed_tickers"]) < 80:
                    price_result["failed_tickers"].append(
                        {
                            "ticker": item.get("ticker"),
                            "yahoo_symbol": item.get("yahoo_symbol"),
                            "error_message": item.get("error_message") or "Price batch failed",
                        }
                    )
                continue
            price_result["success_count"] += 1
            price_result["records_seen"] += int(item.get("records_seen") or 0)
            price_result["records_written"] += int(item.get("records_written") or 0)

    price_result["ok"] = price_result["success_count"] > 0 and price_result["failure_count"] == 0
    price_result["partial"] = price_result["success_count"] > 0 and price_result["failure_count"] > 0
    if price_result["success_count"] == 0:
        raise RuntimeError("Smart Refresh konnte keine Kursdaten aktualisieren.")
    return price_result


def _merge_price_symbols(symbols: list[Any], *, benchmark_ticker: str) -> list[Any]:
    by_ticker = {str(symbol.source_ticker).upper(): symbol for symbol in symbols if str(symbol.source_ticker).strip()}
    for ticker in [*MARKET_CORE_PRICE_TICKERS, *VOLATILITY_TICKERS, *SECTOR_ETF_TICKERS, benchmark_ticker, "SPY"]:
        clean = ticker.strip().upper()
        if clean and clean not in by_ticker:
            by_ticker[clean] = _SimplePriceSymbol(source_ticker=clean, yahoo_symbol=clean)
    return list(by_ticker.values())


def _refresh_fundamentals(
    job_id: str,
    payload: dict[str, Any],
    *,
    result: dict[str, Any],
    action_index: int,
    total_actions: int,
) -> dict[str, Any]:
    tickers = resolve_fundamental_tickers(payload)
    include_holders = bool(payload.get("include_holders", True))
    incremental = _normalize_bool(payload.get("incremental"), default=True)
    max_refresh_count = _normalize_fundamental_max_refresh_count(
        payload.get("fundamental_max_refresh_count") or payload.get("fundamental_batch_limit")
    )
    freshness_days = _normalize_fundamental_freshness_days(payload.get("fundamental_freshness_days"))
    max_action_seconds = _normalize_seconds(
        payload.get("fundamental_action_max_seconds") or payload.get("max_action_seconds"),
        default=DEFAULT_FUNDAMENTAL_ACTION_MAX_SECONDS,
        min_value=60,
        max_value=6 * 60 * 60,
    )
    latest_states = _latest_fundamental_states(tickers) if incremental else {}
    selected_tickers, skipped_current_count, deferred_count = _select_fundamental_work(
        tickers,
        latest_states=latest_states,
        incremental=incremental,
        max_refresh_count=max_refresh_count,
        freshness_days=freshness_days,
    )
    fundamental_result: dict[str, Any] = {
        "ok": False,
        "job_type": "refresh_fundamentals",
        "tickers": selected_tickers,
        "ticker_count": len(tickers),
        "selected_ticker_count": len(selected_tickers),
        "pending_count": len(selected_tickers) + deferred_count,
        "max_refresh_count": max_refresh_count,
        "freshness_days": freshness_days,
        "include_holders": include_holders,
        "incremental": incremental,
        "success_count": 0,
        "skipped_count": skipped_current_count,
        "deferred_count": deferred_count,
        "failure_count": 0,
        "failed_tickers": [],
        "records_seen": 0,
        "records_written": 0,
        "max_action_seconds": max_action_seconds,
    }
    total_tickers = max(1, len(selected_tickers))
    base_progress = 8 + int((action_index - 1) / max(1, total_actions) * 82)
    next_progress = 8 + int(action_index / max(1, total_actions) * 82)
    started_at = monotonic()
    for index, ticker in enumerate(selected_tickers, start=1):
        raise_if_cancelled(job_id)
        if _elapsed_seconds(started_at) >= max_action_seconds:
            deferred = total_tickers - index + 1
            fundamental_result["deferred_count"] += deferred
            fundamental_result["stopped_due_to_timeout"] = True
            fundamental_result["partial"] = fundamental_result["success_count"] > 0
            fundamental_result["ok"] = False
            fundamental_result["timeout_message"] = (
                f"Fundamental-Refresh nach {max_action_seconds // 60} Minuten gestoppt; "
                f"{deferred} Ticker werden im nächsten Smart Refresh nachgezogen."
            )
            job_repository.update_progress(
                job_id,
                progress=min(92, base_progress + int(index / total_tickers * max(1, next_progress - base_progress))),
                step="Fundamentals gestoppt",
                message=str(fundamental_result["timeout_message"]),
                result={**result, "current_fundamental_refresh": fundamental_result},
            )
            if fundamental_result["success_count"] == 0:
                raise RuntimeError(str(fundamental_result["timeout_message"]))
            return fundamental_result
        progress = min(92, base_progress + int(index / total_tickers * max(1, next_progress - base_progress)))
        job_repository.update_progress(
            job_id,
            progress=progress,
            step=f"Fundamentals {index}/{total_tickers}",
            message=f"{ticker}: yfinance/FMP/SEC Fundamental-Cache aktualisieren.",
            result={**result, "current_fundamental_refresh": fundamental_result},
        )
        try:
            item = refresh_fundamentals_for_ticker(ticker, include_holders=include_holders)
        except Exception as exc:
            fundamental_result["failure_count"] += 1
            if len(fundamental_result["failed_tickers"]) < 80:
                fundamental_result["failed_tickers"].append(
                    {"ticker": ticker, "error_message": f"{type(exc).__name__}: {exc}"}
                )
            continue
        fundamental_result["success_count"] += 1
        fundamental_result["records_seen"] += int(item.get("records_seen") or 0)
        fundamental_result["records_written"] += int(item.get("records_written") or 0)

    fundamental_result["ok"] = (
        (fundamental_result["success_count"] > 0 or fundamental_result["skipped_count"] > 0)
        and fundamental_result["failure_count"] == 0
    )
    fundamental_result["partial"] = (
        (fundamental_result["success_count"] > 0 and fundamental_result["failure_count"] > 0)
        or fundamental_result["deferred_count"] > 0
    )
    if fundamental_result["deferred_count"] > 0:
        fundamental_result["stopped_due_to_limit"] = True
        fundamental_result["continuation_message"] = (
            f"{fundamental_result['deferred_count']} Fundamental-Ticker wurden auf den nächsten Smart Refresh vertagt."
        )
    if tickers and fundamental_result["success_count"] == 0 and fundamental_result["skipped_count"] > 0:
        fundamental_result["ok"] = True
        fundamental_result["skipped"] = True
        fundamental_result["reason"] = "Fundamental-Cache war bereits aktuell und vollständig."
        return fundamental_result
    if selected_tickers and fundamental_result["success_count"] == 0:
        raise RuntimeError("Smart Refresh konnte keine Fundamentals aktualisieren.")
    if not tickers:
        fundamental_result["ok"] = True
        fundamental_result["skipped"] = True
        fundamental_result["reason"] = "Keine getrackten Ticker für Fundamental-Refresh."
    return fundamental_result


def _select_fundamental_work(
    tickers: list[str],
    *,
    latest_states: dict[str, Any],
    incremental: bool,
    max_refresh_count: int,
    freshness_days: int,
) -> tuple[list[str], int, int]:
    freshness_cutoff = datetime.now(UTC).date() - timedelta(days=max(0, freshness_days - 1))
    if not incremental:
        selected = tickers[:max_refresh_count]
        return selected, 0, max(0, len(tickers) - len(selected))

    skipped_current_count = 0
    pending: list[str] = []
    for ticker in tickers:
        latest_state = latest_states.get(ticker)
        is_current = (
            latest_state is not None
            and latest_state.latest_date is not None
            and latest_state.latest_date >= freshness_cutoff
            and latest_state.complete
        )
        if is_current:
            skipped_current_count += 1
            continue
        pending.append(ticker)

    pending.sort(
        key=lambda ticker: (
            latest_states[ticker].latest_date
            if ticker in latest_states and latest_states[ticker].latest_date is not None
            else date.min,
            ticker,
        )
    )
    selected = pending[:max_refresh_count]
    return selected, skipped_current_count, max(0, len(pending) - len(selected))


def _latest_fundamental_states(tickers: list[str]) -> dict[str, Any]:
    try:
        return fundamentals_repository.latest_fundamental_refresh_states(tickers)
    except fundamentals_repository.FundamentalsRepositoryUnavailable:
        return {}


def _incomplete_fundamental_tickers(payload: dict[str, Any]) -> list[str]:
    tickers = _resolve_fundamental_quality_tickers(payload)
    if not tickers:
        return []
    latest_states = _latest_fundamental_states(tickers)
    incomplete: list[str] = []
    for ticker in tickers:
        latest_state = latest_states.get(ticker)
        if latest_state is None or latest_state.latest_date is None or not latest_state.complete:
            incomplete.append(ticker)
    return incomplete[:80]


def _resolve_fundamental_quality_tickers(payload: dict[str, Any]) -> list[str]:
    limit = _normalize_fundamental_limit(payload.get("fundamental_limit") or payload.get("limit_universe") or 80)
    explicit = resolve_universe_tickers(
        explicit_tickers=payload.get("tickers"),
        universe_key=None,
        fallback=[],
        limit=limit,
    )
    if explicit:
        return explicit

    universe_key = str(payload.get("fundamental_universe") or payload.get("universe") or "").strip().lower()
    mode = str(payload.get("mode") or "").strip().lower()
    if universe_key in {"tracked", "workspace", "open_positions", "recent"} or (mode == "tracked" and not universe_key):
        return _tracked_fundamental_quality_tickers(limit=limit)

    return resolve_fundamental_tickers(payload)


def _tracked_fundamental_quality_tickers(*, limit: int) -> list[str]:
    tickers: list[str] = []
    try:
        tickers.extend(row.ticker for row in portfolio_repository.list_open_positions())
    except portfolio_repository.PortfolioRepositoryUnavailable:
        pass

    workspace = get_workspace_state()
    tickers.extend(workspace.watchlist)
    tickers.extend(workspace.recent_tickers)
    return _dedupe_tickers(tickers)[:limit]


def _dedupe_tickers(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip().upper()
        if clean and clean not in out:
            out.append(clean)
    return out


def _refresh_sec13f(
    job_id: str,
    payload: dict[str, Any],
    *,
    result: dict[str, Any],
    action_index: int,
    total_actions: int,
) -> dict[str, Any]:
    if not str(get_runtime_config_value("SEC_USER_AGENT") or "").strip():
        return {
            "ok": False,
            "skipped": True,
            "job_type": "refresh_sec13f",
            "reason": "SEC_USER_AGENT fehlt. Trage ihn im Setup/Security-Bereich ein; der nächste Smart-Refresh zieht 13F automatisch nach.",
        }

    sec13f_result: dict[str, Any] = {
        "ok": False,
        "job_type": "refresh_sec13f",
        "source": "sec",
    }
    base_progress = 8 + int((action_index - 1) / max(1, total_actions) * 82)
    next_progress = 8 + int(action_index / max(1, total_actions) * 82)

    def progress_callback(progress: int, step: str, message: str, partial: dict[str, Any]) -> None:
        raise_if_cancelled(job_id)
        sec13f_result.update(partial)
        scaled_progress = min(92, base_progress + int(progress / 100 * max(1, next_progress - base_progress)))
        job_repository.update_progress(
            job_id,
            progress=scaled_progress,
            step=step,
            message=message,
            result={**result, "current_sec13f_refresh": sec13f_result},
        )

    sec13f_result = refresh_institutional_13f_from_sec(payload, progress_callback=progress_callback)
    sec13f_result["job_type"] = "refresh_sec13f"
    return sec13f_result


@dataclass(frozen=True)
class _SimplePriceSymbol:
    source_ticker: str
    yahoo_symbol: str


def _freshness_summary(freshness: FreshnessResponse) -> dict[str, dict[str, Any]]:
    return {item.name: {"status": item.status, "as_of": item.as_of, "lag_minutes": item.lag_minutes} for item in freshness.services}


def _is_missing(freshness: ServiceFreshness | None) -> bool:
    return freshness is None or freshness.status == "missing"


def _is_stale(freshness: ServiceFreshness | None) -> bool:
    return bool(freshness and freshness.status == "stale")


def _universe_needs_refresh(status: UniverseStatusResponse) -> bool:
    if status.source == "fallback" or status.member_count < 350:
        return True
    if status.updated_at is None:
        return True
    return status.updated_at.astimezone(UTC) < datetime.now(UTC) - timedelta(days=7)


def _scheduled_or_forced(payload: dict) -> bool:
    mode = str(payload.get("mode") or "").strip().lower()
    if mode == "scheduled":
        return True
    value = payload.get("force_market_refresh")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_range(value: object) -> PriceRange:
    clean = str(value).strip()
    if clean in {"1m", "3m", "6m", "1y", "2y", "5y"}:
        return clean  # type: ignore[return-value]
    return "6m"


def _normalize_limit(value: object) -> int:
    try:
        return max(350, min(10000, int(value)))
    except (TypeError, ValueError):
        return 10000


def _normalize_fundamental_limit(value: object) -> int:
    try:
        return max(1, min(10000, int(value)))
    except (TypeError, ValueError):
        return 80


def _normalize_fundamental_max_refresh_count(value: object) -> int:
    try:
        return max(1, min(1000, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FUNDAMENTAL_MAX_REFRESH_COUNT


def _normalize_fundamental_freshness_days(value: object) -> int:
    try:
        return max(1, min(90, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FUNDAMENTAL_FRESHNESS_DAYS


def _normalize_13f_limit(value: object) -> int:
    try:
        return max(1, min(10000, int(value)))
    except (TypeError, ValueError):
        return 120


def _normalize_dataset_count(value: object) -> int:
    try:
        return max(2, min(8, int(value)))
    except (TypeError, ValueError):
        return 2


def _normalize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_days(value: object) -> int:
    try:
        return max(90, min(2500, int(value)))
    except (TypeError, ValueError):
        return 550


def _normalize_seconds(value: object, *, default: int, min_value: int, max_value: int) -> int:
    try:
        return max(min_value, min(max_value, int(value)))
    except (TypeError, ValueError):
        return default


def _normalize_batch_size(value: object) -> int:
    try:
        return max(1, min(250, int(value)))
    except (TypeError, ValueError):
        return 50


def _normalize_overlap_days(value: object) -> int:
    try:
        return max(0, min(30, int(value)))
    except (TypeError, ValueError):
        return 1


def _elapsed_seconds(started_at: float) -> int:
    return max(0, int(monotonic() - started_at))
