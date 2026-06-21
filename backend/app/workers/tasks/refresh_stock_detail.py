from __future__ import annotations

from typing import Any

from app.services.fundamentals import refresh_fundamentals_for_ticker
from app.services.prices import PriceRange, refresh_price_cache_for_ticker
from app.services.relative_strength import DEFAULT_RS_BENCHMARK_TICKER, refresh_relative_strength_ratings
from app.services.sec13f import refresh_institutional_13f_from_sec
from app.services.settings import get_runtime_config_value
from app.repositories import jobs as job_repository
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_stock_detail")
def refresh_stock_detail(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_stock_detail",
            payload,
            requested_by=str(payload.get("source") or "stock_detail"),
        )

    tickers = _normalize_tickers(payload.get("tickers") or [payload.get("ticker")])
    range_key = _normalize_range(payload.get("range") or "2y")
    benchmark_ticker = str(payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER).strip().upper()
    include_13f = _normalize_bool(payload.get("include_13f"), default=False)
    include_fundamentals = _normalize_bool(payload.get("include_fundamentals"), default=True)
    include_rs = _normalize_bool(payload.get("include_rs"), default=True)
    include_prices = _normalize_bool(payload.get("include_prices"), default=True)
    incremental = _normalize_bool(payload.get("incremental"), default=True)

    result: dict[str, Any] = {
        "ok": False,
        "job_type": "refresh_stock_detail",
        "tickers": tickers,
        "ticker_count": len(tickers),
        "range": range_key,
        "benchmark_ticker": benchmark_ticker,
        "include_prices": include_prices,
        "success_count": 0,
        "failure_count": 0,
        "partial": False,
        "items": [],
    }

    job_repository.mark_running(job.job_id, step="Aktien-Detailrefresh startet")
    try:
        if not tickers:
            job_repository.mark_failed(job.job_id, error_message="Kein Ticker für Aktien-Detailrefresh übergeben.", result=result)
            return result

        total = len(tickers)
        for index, ticker in enumerate(tickers, start=1):
            raise_if_cancelled(job.job_id)
            item_result = _refresh_one_stock(
                job.job_id,
                ticker,
                range_key=range_key,
                benchmark_ticker=benchmark_ticker,
                include_13f=include_13f,
                include_fundamentals=include_fundamentals,
                include_prices=include_prices,
                include_rs=include_rs,
                incremental=incremental,
                base_progress=5 + int((index - 1) / max(1, total) * 90),
                next_progress=5 + int(index / max(1, total) * 90),
                parent_result=result,
            )
            result["items"].append(item_result)
            if item_result["ok"]:
                result["success_count"] += 1
            else:
                result["failure_count"] += 1

        result["ok"] = result["success_count"] > 0 and result["failure_count"] == 0
        result["partial"] = result["success_count"] > 0 and result["failure_count"] > 0
        if result["success_count"] == 0:
            job_repository.mark_failed(
                job.job_id,
                error_message="Kein Ticker konnte vollständig aktualisiert werden.",
                result=result,
            )
            return result

        message = "Aktien-Detaildaten aktualisiert."
        if result["partial"]:
            message = f"Aktien-Detaildaten teilweise aktualisiert; {result['failure_count']} Ticker unvollständig."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def _refresh_one_stock(
    job_id: str,
    ticker: str,
    *,
    range_key: PriceRange,
    benchmark_ticker: str,
    include_13f: bool,
    include_fundamentals: bool,
    include_prices: bool,
    include_rs: bool,
    incremental: bool,
    base_progress: int,
    next_progress: int,
    parent_result: dict[str, Any],
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ticker": ticker,
        "ok": False,
        "steps": {},
        "errors": [],
        "warnings": [],
    }

    def update(progress_fraction: float, step: str, message: str) -> None:
        progress = min(95, base_progress + int(progress_fraction * max(1, next_progress - base_progress)))
        job_repository.update_progress(
            job_id,
            progress=progress,
            step=step,
            message=message,
            result={**parent_result, "current_stock_refresh": item},
        )

    if include_prices:
        update(0.05, f"{ticker} Kursdaten laden", f"{ticker}: Price-Cache wird aktualisiert.")
        item["steps"]["price"] = _safe_step(
            lambda: refresh_price_cache_for_ticker(ticker, range_key=range_key, incremental=incremental)
        )
    else:
        item["steps"]["price"] = {
            "ok": True,
            "skipped": True,
            "reason": "Kursrefresh wurde von der Aktien-Detailseite separat ausgelöst.",
        }

    if include_rs:
        if include_prices:
            update(0.22, f"{benchmark_ticker} Benchmark laden", f"{benchmark_ticker}: Benchmark-Kurse für RS prüfen.")
            item["steps"]["benchmark_price"] = _safe_step(
                lambda: refresh_price_cache_for_ticker(benchmark_ticker, range_key=range_key, incremental=incremental)
            )
        else:
            item["steps"]["benchmark_price"] = {
                "ok": True,
                "skipped": True,
                "reason": "Benchmark-Kursrefresh wurde im automatischen Detailjob übersprungen.",
            }
        update(0.38, f"{ticker} Relative Stärke berechnen", f"{ticker}: RS-Rating gegen {benchmark_ticker} berechnen.")
        item["steps"]["relative_strength"] = _safe_step(
            lambda: refresh_relative_strength_ratings(tickers=[ticker], benchmark_ticker=benchmark_ticker)
        )

    if include_fundamentals:
        update(0.58, f"{ticker} Fundamentals laden", f"{ticker}: yfinance/FMP/SEC Fundamental-Cache aktualisieren.")
        item["steps"]["fundamentals"] = _safe_step(lambda: refresh_fundamentals_for_ticker(ticker, include_holders=True))

    if include_13f:
        update(0.78, f"{ticker} 13F/SEC prüfen", f"{ticker}: institutionelle 13F-Trends für den Ticker aktualisieren.")
        item["steps"]["sec13f"] = _refresh_13f_step(ticker)

    failed_steps = {
        name: step
        for name, step in item["steps"].items()
        if not _step_ok(step, allow_skipped=name == "sec13f")
    }
    warning_steps = {
        name: step
        for name, step in item["steps"].items()
        if name == "sec13f" and not _step_ok(step, allow_skipped=True)
    }
    blocking_failed_steps = {name: step for name, step in failed_steps.items() if name != "sec13f"}
    item["errors"] = [
        f"{name}: {step.get('error_message') or step.get('reason') or 'unvollständig'}"
        for name, step in blocking_failed_steps.items()
    ]
    item["warnings"] = [
        f"{name}: {step.get('error_message') or step.get('reason') or 'keine Daten gespeichert'}"
        for name, step in warning_steps.items()
    ]
    item["ok"] = not blocking_failed_steps
    return item


def _refresh_13f_step(ticker: str) -> dict[str, Any]:
    if not str(get_runtime_config_value("SEC_USER_AGENT") or "").strip():
        return {
            "ok": False,
            "skipped": True,
            "reason": "SEC_USER_AGENT fehlt. Trage ihn im Setup/Security-Bereich ein, damit 13F-Daten geladen werden können.",
        }
    return _safe_step(
        lambda: refresh_institutional_13f_from_sec(
            {
                "mode": "stock_detail",
                "source": "stock_detail",
                "tickers": [ticker],
                "limit_universe": 1,
                "dataset_count": 2,
            }
        )
    )


def _safe_step(callback) -> dict[str, Any]:
    try:
        result = callback()
    except Exception as exc:
        return {"ok": False, "error_message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, dict):
        return result
    return {"ok": True, "result": result}


def _step_ok(step: dict[str, Any], *, allow_skipped: bool = False) -> bool:
    if allow_skipped and step.get("skipped"):
        return True
    if step.get("ok") is True:
        return True
    if step.get("records_written") or step.get("records_seen"):
        return True
    return False


def _normalize_tickers(value: object) -> list[str]:
    raw = value if isinstance(value, list | tuple | set) else [value]
    out: list[str] = []
    for item in raw:
        clean = str(item or "").strip().upper()
        if clean and clean not in out:
            out.append(clean[:32])
    return out[:20]


def _normalize_range(value: object) -> PriceRange:
    clean = str(value or "").strip()
    if clean in {"1m", "3m", "6m", "1y", "2y", "5y"}:
        return clean  # type: ignore[return-value]
    return "2y"


def _normalize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
