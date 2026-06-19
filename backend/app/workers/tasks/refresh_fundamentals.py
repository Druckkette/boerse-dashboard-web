from __future__ import annotations

from datetime import date

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import fundamentals as fundamentals_repository
from app.repositories import portfolio as portfolio_repository
from app.repositories import jobs as job_repository
from app.services.fundamentals import refresh_fundamentals_for_ticker
from app.services.workspace import get_workspace_state
from app.services.universes import resolve_universe_tickers
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_fundamentals")
def refresh_fundamentals(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_fundamentals",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )

    tickers = resolve_fundamental_tickers(payload)
    include_holders = bool(payload.get("include_holders", True))
    incremental = _normalize_bool(payload.get("incremental"), default=False)
    latest_dates = _latest_fundamental_dates(tickers) if incremental else {}
    fail_fast = bool(payload.get("fail_fast", False))
    result: dict = {
        "ok": False,
        "job_type": "refresh_fundamentals",
        "tickers": tickers,
        "ticker_count": len(tickers),
        "include_holders": include_holders,
        "incremental": incremental,
        "success_count": 0,
        "skipped_count": 0,
        "failure_count": 0,
        "failed_tickers": [],
        "records_seen": 0,
        "records_written": 0,
        "items": [],
    }

    job_repository.mark_running(job.job_id, step="Fundamental-Refresh startet")
    try:
        total = max(1, len(tickers))
        for index, ticker in enumerate(tickers, start=1):
            raise_if_cancelled(job.job_id)
            latest_date = latest_dates.get(ticker)
            if incremental and latest_date is not None and latest_date >= date.today():
                result["skipped_count"] += 1
                result["items"].append(
                    {
                        "ticker": ticker,
                        "ok": True,
                        "skipped": True,
                        "reason": "Fundamental-Snapshot ist heute bereits aktuell.",
                        "as_of": latest_date.isoformat(),
                        "records_seen": 0,
                        "records_written": 0,
                    }
                )
                continue
            job_repository.update_progress(
                job.job_id,
                progress=min(90, 10 + int(index / total * 80)),
                step=f"{ticker} Fundamentals laden",
                message=f"{ticker}: kompakter yfinance-Snapshot wird im Worker geladen.",
                result=result,
            )
            try:
                item = refresh_fundamentals_for_ticker(ticker, include_holders=include_holders)
            except Exception as exc:
                item = {
                    "ticker": ticker,
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

            result["items"].append(item)
            result["success_count"] += 1
            result["records_seen"] += int(item.get("records_seen") or 0)
            result["records_written"] += int(item.get("records_written") or 0)

        result["ok"] = result["failure_count"] == 0 and (result["success_count"] > 0 or result["skipped_count"] > 0)
        result["partial"] = result["success_count"] > 0 and result["failure_count"] > 0
        if result["success_count"] == 0:
            job_repository.mark_failed(
                job.job_id,
                error_message="Kein Ticker konnte mit Fundamentals aktualisiert werden.",
                result=result,
            )
            return result

        message = "Fundamental-Cache aktualisiert."
        if result["failure_count"]:
            message = f"Fundamental-Cache teilweise aktualisiert; {result['failure_count']} Ticker fehlgeschlagen."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def resolve_fundamental_tickers(payload: dict | None = None) -> list[str]:
    payload = payload or {}
    limit = _normalize_limit(payload.get("fundamental_limit") or payload.get("limit_universe") or payload.get("limit") or 50)
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
        tracked = _tracked_fundamental_tickers(limit=limit)
        if tracked:
            return tracked

    return resolve_universe_tickers(
        explicit_tickers=None,
        universe_key=payload.get("universe"),
        fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
        limit=limit,
    )


def _tracked_fundamental_tickers(*, limit: int) -> list[str]:
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


def _normalize_limit(value: object) -> int:
    try:
        return max(1, min(5000, int(value)))
    except (TypeError, ValueError):
        return 50


def _latest_fundamental_dates(tickers: list[str]) -> dict[str, date]:
    try:
        return fundamentals_repository.latest_fundamental_dates(tickers)
    except fundamentals_repository.FundamentalsRepositoryUnavailable:
        return {}


def _normalize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
