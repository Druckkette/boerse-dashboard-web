from __future__ import annotations

from typing import Literal

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS, SECTOR_ETF_TICKERS
from app.domain.market.volatility import VOLATILITY_TICKERS
from app.repositories import jobs as job_repository
from app.services.prices import PriceRange, refresh_price_cache_for_ticker
from app.services.universes import resolve_universe_price_symbols
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


PriceRefreshPreset = Literal["all", "market_core", "volatility", "sector"]
DEFAULT_PRICE_REFRESH_TICKERS = list(
    dict.fromkeys([*DEFAULT_MARKET_UNIVERSE_TICKERS, *VOLATILITY_TICKERS, *SECTOR_ETF_TICKERS])
)
PRICE_REFRESH_PRESETS: dict[PriceRefreshPreset, list[str]] = {
    "all": DEFAULT_PRICE_REFRESH_TICKERS,
    "market_core": DEFAULT_MARKET_UNIVERSE_TICKERS,
    "volatility": VOLATILITY_TICKERS,
    "sector": SECTOR_ETF_TICKERS,
}


@celery_app.task(bind=True, name="refresh_prices")
def refresh_prices(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("refresh_prices", payload, requested_by=str(payload.get("source") or "scheduler"))

    preset = _normalize_preset(payload.get("preset") or payload.get("universe") or "all")
    explicit_tickers = payload.get("tickers")
    limit = _normalize_limit(payload.get("limit_universe") or payload.get("limit") or 50)
    symbols = resolve_universe_price_symbols(
        explicit_tickers=explicit_tickers,
        universe_key=payload.get("universe"),
        fallback=PRICE_REFRESH_PRESETS[preset],
        limit=limit,
    )
    tickers = [symbol.source_ticker for symbol in symbols]
    range_key = _normalize_range(payload.get("range") or "1y")
    fail_fast = bool(payload.get("fail_fast") or False)
    result: dict = {
        "ok": False,
        "job_type": "refresh_prices",
        "range": range_key,
        "preset": preset,
        "tickers": tickers,
        "ticker_count": len(tickers),
        "resolved_symbols": [
            {
                "source_ticker": symbol.source_ticker,
                "yahoo_symbol": symbol.yahoo_symbol,
                "status": symbol.status,
                "source": symbol.source,
            }
            for symbol in symbols
        ],
        "success_count": 0,
        "failure_count": 0,
        "failed_tickers": [],
        "records_seen": 0,
        "records_written": 0,
        "items": [],
    }

    job_repository.mark_running(job.job_id, step="Price-Cache-Refresh startet")
    try:
        total = max(1, len(symbols))
        for index, symbol in enumerate(symbols, start=1):
            ticker = symbol.source_ticker
            raise_if_cancelled(job.job_id)
            progress = min(90, 10 + int(index / total * 80))
            job_repository.update_progress(
                job.job_id,
                progress=progress,
                step=f"{ticker} von yfinance laden",
                message=f"{ticker}: tägliche OHLC-Bars über {symbol.yahoo_symbol} werden aktualisiert.",
                result=result,
            )
            try:
                item = refresh_price_cache_for_ticker(
                    ticker,
                    range_key=range_key,
                    yahoo_symbol=symbol.yahoo_symbol,
                )
            except Exception as exc:
                item = {
                    "ticker": ticker,
                    "yahoo_symbol": symbol.yahoo_symbol,
                    "ok": False,
                    "records_seen": 0,
                    "records_written": 0,
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "source": "yfinance",
                }
                result["failure_count"] += 1
                result["failed_tickers"].append(ticker)
                result["items"].append(item)
                if fail_fast:
                    raise
                continue

            item["ok"] = True
            result["items"].append(item)
            result["success_count"] += 1
            result["records_seen"] += int(item.get("records_seen") or 0)
            result["records_written"] += int(item.get("records_written") or 0)

        result["ok"] = result["failure_count"] == 0 and result["success_count"] > 0
        result["partial"] = result["success_count"] > 0 and result["failure_count"] > 0
        if result["success_count"] == 0:
            job_repository.mark_failed(
                job.job_id,
                error_message="Kein Ticker konnte aktualisiert werden.",
                result=result,
            )
            return result

        message = "Price-Cache aktualisiert."
        if result["failure_count"]:
            message = f"Price-Cache teilweise aktualisiert; {result['failure_count']} Ticker fehlgeschlagen."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def _normalize_tickers(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    tickers = [item.strip().upper() for item in raw if item and item.strip()]
    return list(dict.fromkeys(tickers))[:50]


def _normalize_range(value: object) -> PriceRange:
    clean = str(value).strip()
    if clean in {"1m", "3m", "6m", "1y", "2y", "5y"}:
        return clean  # type: ignore[return-value]
    return "1y"


def _normalize_preset(value: object) -> PriceRefreshPreset:
    clean = str(value).strip().lower()
    if clean in PRICE_REFRESH_PRESETS:
        return clean  # type: ignore[return-value]
    return "all"


def _normalize_limit(value: object) -> int:
    try:
        return max(1, min(5_000, int(value)))
    except (TypeError, ValueError):
        return 50
