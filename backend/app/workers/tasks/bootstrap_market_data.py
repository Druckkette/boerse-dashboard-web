from __future__ import annotations

from typing import Any

from app.domain.market.constants import (
    DEFAULT_MARKET_UNIVERSE_KEY,
    DEFAULT_MARKET_UNIVERSE_TICKERS,
    MARKET_CORE_PRICE_TICKERS,
    SECTOR_ETF_TICKERS,
)
from app.domain.market.volatility import VOLATILITY_TICKERS
from app.domain.sell.service import monitor_open_positions
from app.repositories import jobs as job_repository
from app.services.market import refresh_market_breadth
from app.services.prices import PriceRange, refresh_price_cache_for_ticker
from app.services.relative_strength import DEFAULT_RS_BENCHMARK_TICKER, refresh_relative_strength_ratings
from app.services.universes import (
    refresh_us_common_stock_universe,
    resolve_universe_price_symbols,
)
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="bootstrap_market_data")
def bootstrap_market_data(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "bootstrap_market_data",
            payload,
            requested_by=str(payload.get("source") or "dashboard"),
        )
    elif job.status == "done" and isinstance(job.result, dict) and job.result.get("ok") is True:
        return {**job.result, "already_completed": True}

    mode = str(payload.get("mode") or "initial").strip().lower()
    is_initial = mode in {"initial", "bootstrap", "full"}
    universe_key = str(payload.get("universe") or DEFAULT_MARKET_UNIVERSE_KEY).strip() or DEFAULT_MARKET_UNIVERSE_KEY
    limit_universe = _normalize_limit(payload.get("limit_universe") or 5000)
    range_key = _normalize_range(payload.get("range") or ("2y" if is_initial else "6m"))
    breadth_lookback_days = _normalize_days(payload.get("breadth_lookback_days") or payload.get("lookback_days") or 550)
    rs_lookback_days = _normalize_days(payload.get("rs_lookback_days") or 430)
    benchmark_ticker = str(payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER).strip().upper()

    result: dict[str, Any] = {
        "ok": False,
        "job_type": "bootstrap_market_data",
        "mode": "initial" if is_initial else "update",
        "universe": universe_key,
        "limit_universe": limit_universe,
        "range": range_key,
        "breadth_lookback_days": breadth_lookback_days,
        "rs_lookback_days": rs_lookback_days,
        "benchmark_ticker": benchmark_ticker,
        "steps": [],
    }
    result = _resume_result(job.result, result)
    completed_steps = set(_normalize_steps(result.get("steps")))

    job_repository.mark_running(job.job_id, step="Marktdaten-Bootstrap startet")
    try:
        if "universe" in completed_steps:
            job_repository.update_progress(
                job.job_id,
                progress=7,
                step="Aktienuniversum bereits geladen",
                message="Bootstrap wurde fortgesetzt; Universe-Refresh ist bereits abgeschlossen.",
                result=result,
            )
        elif is_initial or payload.get("refresh_universe", True):
            raise_if_cancelled(job.job_id)
            job_repository.update_progress(
                job.job_id,
                progress=5,
                step="Aktienuniversum laden",
                message="US Common Stocks werden über Nasdaq Trader aktualisiert.",
                result=result,
            )
            universe_result = refresh_us_common_stock_universe()
            result["universe_refresh"] = _compact_step_result(universe_result)
            result["steps"].append("universe")
            completed_steps.add("universe")

        universe_symbols = resolve_universe_price_symbols(
            explicit_tickers=payload.get("tickers"),
            universe_key=universe_key,
            fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
            limit=limit_universe,
        )
        universe_tickers = [symbol.source_ticker for symbol in universe_symbols]
        if not payload.get("tickers") and len(universe_tickers) < 350:
            raise RuntimeError(
                "Aktienuniversum ist zu klein für die Streamlit-kompatible Marktbreite "
                f"({len(universe_tickers)} Titel). Bitte Universe-Refresh prüfen."
            )

        price_symbols = _merge_price_symbols(universe_symbols, benchmark_ticker=benchmark_ticker)
        result["universe_size"] = len(universe_tickers)
        result["price_ticker_count"] = len(price_symbols)
        if "prices" in completed_steps and result.get("prices"):
            price_result = dict(result["prices"])
            job_repository.update_progress(
                job.job_id,
                progress=71,
                step="Price Cache bereits geladen",
                message="Bootstrap wurde fortgesetzt; Price Cache ist bereits abgeschlossen.",
                result=result,
            )
        else:
            price_result = _refresh_prices_for_symbols(
                job_id=job.job_id,
                symbols=price_symbols,
                range_key=range_key,
                result=result,
                existing_result=result.get("prices") if isinstance(result.get("prices"), dict) else None,
            )
            result["prices"] = price_result
            if "prices" not in completed_steps:
                result["steps"].append("prices")
                completed_steps.add("prices")

        raise_if_cancelled(job.job_id)
        if "breadth" in completed_steps and result.get("breadth"):
            breadth_result = dict(result["breadth"])
            job_repository.update_progress(
                job.job_id,
                progress=83,
                step="Marktbreite bereits berechnet",
                message="Bootstrap wurde fortgesetzt; Marktbreite ist bereits abgeschlossen.",
                result=result,
            )
        else:
            job_repository.update_progress(
                job.job_id,
                progress=72,
                step="Marktbreite berechnen",
                message="Advancers/Decliners, RANA-McClellan, NH/NL und SMA-Breite werden aus dem Price Cache berechnet.",
                result=result,
            )
            breadth_result = refresh_market_breadth(
                tickers=universe_tickers,
                universe=universe_key,
                lookback_days=breadth_lookback_days,
            )
            result["breadth"] = _compact_step_result(breadth_result)
            result["steps"].append("breadth")
            completed_steps.add("breadth")

        raise_if_cancelled(job.job_id)
        if "relative_strength" in completed_steps and result.get("relative_strength"):
            rs_result = dict(result["relative_strength"])
            job_repository.update_progress(
                job.job_id,
                progress=93,
                step="Relative Stärke bereits berechnet",
                message="Bootstrap wurde fortgesetzt; RS-Ratings sind bereits abgeschlossen.",
                result=result,
            )
        else:
            job_repository.update_progress(
                job.job_id,
                progress=84,
                step="Relative Stärke berechnen",
                message=f"RS-Ratings werden gegen {benchmark_ticker} aus gecachten Kursen berechnet.",
                result=result,
            )
            rs_result = refresh_relative_strength_ratings(
                tickers=universe_tickers,
                benchmark_ticker=benchmark_ticker,
                lookback_days=rs_lookback_days,
                source="computed",
            )
            result["relative_strength"] = _compact_step_result(rs_result)
            result["steps"].append("relative_strength")
            completed_steps.add("relative_strength")

        raise_if_cancelled(job.job_id)
        if "position_monitor" in completed_steps and result.get("position_monitor"):
            monitor_result = dict(result["position_monitor"])
        else:
            job_repository.update_progress(
                job.job_id,
                progress=94,
                step="Positionsmonitor prüfen",
                message="Offene Positionen werden gegen Sell-Engine und Price Cache geprüft, falls ein Depot importiert ist.",
                result=result,
            )
            monitor_result = monitor_open_positions(tickers=None)
            result["position_monitor"] = _compact_step_result(monitor_result)
            result["steps"].append("position_monitor")

        result["ok"] = bool(price_result.get("success_count")) and not breadth_result.get("skipped")
        result["partial"] = bool(price_result.get("failure_count")) or bool(rs_result.get("skipped")) or bool(monitor_result.get("skipped"))
        message = "Marktdaten vollständig initialisiert." if is_initial else "Marktdaten aktualisiert."
        if result["partial"]:
            message += " Einzelne optionale Teile wurden übersprungen oder teilweise geladen."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        result["ok"] = False
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def _refresh_prices_for_symbols(
    *,
    job_id: str,
    symbols: list[dict[str, str]],
    range_key: PriceRange,
    result: dict[str, Any],
    existing_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed_tickers = _normalize_ticker_list((existing_result or {}).get("completed_tickers"))
    price_result: dict[str, Any] = {
        "ok": False,
        "success_count": len(completed_tickers),
        "failure_count": 0,
        "failed_tickers": [],
        "completed_tickers": list(completed_tickers),
        "records_seen": int((existing_result or {}).get("records_seen") or 0),
        "records_written": int((existing_result or {}).get("records_written") or 0),
        "resumed": bool(completed_tickers),
    }
    completed_set = set(completed_tickers)
    total = max(1, len(symbols))
    for index, symbol in enumerate(symbols, start=1):
        raise_if_cancelled(job_id)
        ticker = symbol["source_ticker"]
        yahoo_symbol = symbol["yahoo_symbol"]
        if ticker in completed_set:
            continue
        progress = min(70, 8 + int(index / total * 60))
        if index == 1 or index == total or index % 25 == 0:
            job_repository.update_progress(
                job_id,
                progress=progress,
                step=f"Price Cache {index}/{total}",
                message=f"{ticker} über {yahoo_symbol} laden.",
                result={**result, "prices": price_result},
            )
        try:
            item = refresh_price_cache_for_ticker(ticker, range_key=range_key, yahoo_symbol=yahoo_symbol)
        except Exception as exc:
            price_result["failure_count"] += 1
            if len(price_result["failed_tickers"]) < 80:
                price_result["failed_tickers"].append(
                    {
                        "ticker": ticker,
                        "yahoo_symbol": yahoo_symbol,
                        "error_message": f"{type(exc).__name__}: {exc}",
                    }
                )
            continue

        price_result["success_count"] += 1
        price_result["completed_tickers"].append(ticker)
        completed_set.add(ticker)
        price_result["records_seen"] += int(item.get("records_seen") or 0)
        price_result["records_written"] += int(item.get("records_written") or 0)

    price_result["ok"] = price_result["success_count"] > 0 and price_result["failure_count"] == 0
    price_result["partial"] = price_result["success_count"] > 0 and price_result["failure_count"] > 0
    return price_result


def _resume_result(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(existing, dict) or existing.get("job_type") != "bootstrap_market_data":
        return fresh
    resumed = {**fresh, **existing}
    resumed["ok"] = False
    resumed["mode"] = fresh["mode"]
    resumed["universe"] = fresh["universe"]
    resumed["limit_universe"] = fresh["limit_universe"]
    resumed["range"] = fresh["range"]
    resumed["breadth_lookback_days"] = fresh["breadth_lookback_days"]
    resumed["rs_lookback_days"] = fresh["rs_lookback_days"]
    resumed["benchmark_ticker"] = fresh["benchmark_ticker"]
    resumed["steps"] = _normalize_steps(existing.get("steps"))
    resumed["resumed"] = True
    return resumed


def _normalize_steps(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _normalize_ticker_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip().upper() for item in value if str(item).strip()))


def _merge_price_symbols(universe_symbols: list[Any], *, benchmark_ticker: str) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for symbol in universe_symbols:
        source_ticker = str(getattr(symbol, "source_ticker", "")).strip().upper()
        yahoo_symbol = str(getattr(symbol, "yahoo_symbol", "") or source_ticker).strip().upper()
        if source_ticker:
            merged[source_ticker] = {"source_ticker": source_ticker, "yahoo_symbol": yahoo_symbol}
    for ticker in [
        *MARKET_CORE_PRICE_TICKERS,
        *VOLATILITY_TICKERS,
        *SECTOR_ETF_TICKERS,
        benchmark_ticker,
        "SPY",
    ]:
        clean = ticker.strip().upper()
        if clean:
            merged.setdefault(clean, {"source_ticker": clean, "yahoo_symbol": clean})
    return list(merged.values())


def _compact_step_result(value: dict[str, Any]) -> dict[str, Any]:
    compact = {key: item for key, item in value.items() if key not in {"items", "resolved_symbols", "top"}}
    failed = compact.get("failed_tickers")
    if isinstance(failed, list) and len(failed) > 80:
        compact["failed_tickers"] = failed[:80]
        compact["failed_tickers_truncated"] = len(failed) - 80
    return compact


def _normalize_range(value: object) -> PriceRange:
    clean = str(value).strip()
    if clean in {"1m", "3m", "6m", "1y", "2y", "5y"}:
        return clean  # type: ignore[return-value]
    return "2y"


def _normalize_limit(value: object) -> int:
    try:
        return max(350, min(5000, int(value)))
    except (TypeError, ValueError):
        return 5000


def _normalize_days(value: object) -> int:
    try:
        return max(90, min(2500, int(value)))
    except (TypeError, ValueError):
        return 550
