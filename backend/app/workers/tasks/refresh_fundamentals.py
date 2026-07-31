from __future__ import annotations

from datetime import date, timedelta

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import fundamentals as fundamentals_repository
from app.repositories import portfolio as portfolio_repository
from app.repositories import jobs as job_repository
from app.services.earnings import earnings_priority_tickers
from app.services.fundamentals import refresh_fundamentals_for_ticker
from app.services.workspace import get_workspace_state
from app.services.universes import resolve_universe_tickers
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


DEFAULT_MAX_REFRESH_COUNT = 250
DEFAULT_FUNDAMENTAL_FRESHNESS_DAYS = 14


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
    max_refresh_count = _normalize_max_refresh_count(
        payload.get("fundamental_max_refresh_count") or payload.get("fundamental_batch_limit")
    )
    freshness_days = _normalize_freshness_days(payload.get("fundamental_freshness_days"))
    latest_states = _latest_fundamental_states(tickers) if incremental else {}
    priority_tickers = earnings_priority_tickers()
    selected_tickers, skipped_current_count, deferred_count = _select_fundamental_work(
        tickers,
        latest_states=latest_states,
        incremental=incremental,
        max_refresh_count=max_refresh_count,
        freshness_days=freshness_days,
        priority_tickers=priority_tickers,
    )
    fail_fast = bool(payload.get("fail_fast", False))
    result: dict = {
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
        "items": [],
        "earnings_priority_tickers": [
            ticker for ticker in selected_tickers if ticker in set(priority_tickers)
        ],
    }

    job_repository.mark_running(job.job_id, step="Fundamental-Refresh startet")
    try:
        total = max(1, len(selected_tickers))
        for index, ticker in enumerate(selected_tickers, start=1):
            raise_if_cancelled(job.job_id)
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
        result["partial"] = (result["success_count"] > 0 and result["failure_count"] > 0) or result["deferred_count"] > 0
        if result["deferred_count"] > 0:
            result["stopped_due_to_limit"] = True
            result["continuation_message"] = (
                f"{result['deferred_count']} Fundamental-Ticker wurden auf den nächsten Refresh vertagt."
            )
        if result["success_count"] == 0 and result["skipped_count"] > 0:
            job_repository.mark_done(
                job.job_id,
                result=result,
                message="Fundamental-Cache war bereits aktuell und vollständig.",
            )
            return result
        if result["success_count"] == 0:
            job_repository.mark_failed(
                job.job_id,
                error_message="Kein ausgewählter Ticker konnte mit Fundamentals aktualisiert werden.",
                result=result,
            )
            return result

        message = "Fundamental-Cache aktualisiert."
        if result["failure_count"]:
            message = f"Fundamental-Cache teilweise aktualisiert; {result['failure_count']} Ticker fehlgeschlagen."
        elif result["deferred_count"]:
            message = (
                f"Fundamental-Cache teilweise aktualisiert; {result['deferred_count']} Ticker werden im nächsten Lauf fortgesetzt."
            )
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
        return max(1, min(10000, int(value)))
    except (TypeError, ValueError):
        return 50


def _normalize_max_refresh_count(value: object) -> int:
    try:
        return max(1, min(1000, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_REFRESH_COUNT


def _select_fundamental_work(
    tickers: list[str],
    *,
    latest_states: dict[str, fundamentals_repository.FundamentalRefreshState],
    incremental: bool,
    max_refresh_count: int,
    freshness_days: int,
    priority_tickers: list[str] | None = None,
) -> tuple[list[str], int, int]:
    freshness_cutoff = date.today() - timedelta(days=max(0, freshness_days - 1))
    if not incremental:
        selected = tickers[:max_refresh_count]
        return selected, 0, max(0, len(tickers) - len(selected))

    priority = {
        ticker.strip().upper()
        for ticker in (priority_tickers or [])
        if ticker.strip()
    }
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
        if is_current and ticker not in priority:
            skipped_current_count += 1
            continue
        pending.append(ticker)

    pending.sort(
        key=lambda ticker: (
            0 if ticker in priority else 1,
            latest_states[ticker].latest_date
            if ticker in latest_states and latest_states[ticker].latest_date is not None
            else date.min,
            ticker,
        )
    )
    selected = pending[:max_refresh_count]
    return selected, skipped_current_count, max(0, len(pending) - len(selected))


def _latest_fundamental_states(tickers: list[str]) -> dict[str, fundamentals_repository.FundamentalRefreshState]:
    try:
        return fundamentals_repository.latest_fundamental_refresh_states(tickers)
    except fundamentals_repository.FundamentalsRepositoryUnavailable:
        return {}


def _normalize_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_freshness_days(value: object) -> int:
    try:
        return max(1, min(90, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FUNDAMENTAL_FRESHNESS_DAYS
