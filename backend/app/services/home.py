"""Small read-only aggregation for the investor home dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_KEY
from app.domain.stocks.industry_groups import TAXONOMY_VERSION
from app.repositories import earnings as earnings_repository
from app.repositories import industry_group_rs as industry_group_repository
from app.repositories import market as market_repository
from app.repositories import portfolio as portfolio_repository
from app.repositories import prices as price_repository
from app.repositories import sell_state as sell_state_repository
from app.repositories import stock_assessments
from app.services import daily_opportunities
from app.services.industry_group_rs import ALGORITHM_VERSION
from app.services.market_calendar import completed_us_market_session, expected_us_market_session
from app.services.settings import get_data_quality_summary
from app.services.workspace import get_workspace_state


def _read(label: str, callback: Callable[[], Any], errors: list[str], default: Any) -> Any:
    try:
        return callback()
    except Exception:  # noqa: BLE001 - each dashboard panel must degrade independently
        errors.append(label)
        return default


def _phase_label(phase: str | None) -> str:
    return {
        "rot": "Rot", "gelb_startschuss": "Startschuss", "gruen": "Grün",
        "aufwaertstrend": "Aufwärtstrend", "gelb_trend_unter_druck": "Trend unter Druck",
        "neutral": "Neutral",
    }.get(phase or "", "Nicht verfügbar")


def _index_summary(ticker: str, label: str) -> dict[str, Any]:
    """Build a daily index comparison from two canonical persisted closes."""
    completed = completed_us_market_session()
    points = market_repository.load_latest_close_pair(ticker)
    if not points:
        return {"ticker": ticker, "label": label, "status": "missing"}
    current = points[-1]
    previous = points[-2] if len(points) > 1 else None
    status = "available" if current.date == completed.date else "stale"
    if previous is None and status == "available":
        status = "partial"
    change_pct = round((current.close / previous.close - 1) * 100, 2) if previous and previous.close else None
    return {
        "ticker": ticker, "label": label,
        "as_of": current.date.isoformat(),
        "previous_as_of": previous.date.isoformat() if previous else None,
        "close": round(current.close, 2),
        "previous_close": round(previous.close, 2) if previous else None,
        "change_pct": change_pct,
        "status": status,
    }


def _market_summary() -> dict[str, Any]:
    expected = expected_us_market_session()
    completed = completed_us_market_session()
    snapshot = market_repository.get_latest_market_snapshot()
    breadth_rows = market_repository.list_breadth_daily(DEFAULT_MARKET_UNIVERSE_KEY, limit=1)
    breadth = breadth_rows[-1] if breadth_rows else None
    vix = _index_summary("^VIX", "VIX")
    return {
        "session": {
            "phase": "open" if expected.phase == "intraday" else "closed" if expected.phase == "closed" else "unknown",
            "last_completed_as_of": completed.date.isoformat(),
            "current_session_as_of": expected.date.isoformat(),
        },
        "phase": snapshot.ampel_phase if snapshot else None,
        "phase_label": _phase_label(snapshot.ampel_phase if snapshot else None),
        "warning_count": snapshot.warning_count if snapshot else None,
        "breadth": {
            "as_of": breadth.date.isoformat(),
            "pct_above_50sma": breadth.pct_above_50sma,
        } if breadth else None,
        "volatility": {
            "as_of": vix.get("as_of"), "close": vix.get("close"), "status": vix.get("status"),
        },
        "indices": [_index_summary("^GSPC", "S&P 500"), _index_summary("^IXIC", "Nasdaq")],
        "as_of": snapshot.date.isoformat() if snapshot else None,
    }


def _deduplicated_price_bars(rows: list[Any]) -> list[Any]:
    by_date: dict[date, Any] = {}
    fallback = datetime.min.replace(tzinfo=UTC)
    for row in rows:
        if row.close is None:
            continue
        existing = by_date.get(row.date)
        if existing is None or (getattr(row, "fetched_at", None) or fallback) >= (getattr(existing, "fetched_at", None) or fallback):
            by_date[row.date] = row
    return [by_date[key] for key in sorted(by_date)]


def _portfolio_summary() -> dict[str, Any]:
    rows = portfolio_repository.list_open_positions()
    prices_by_ticker = price_repository.list_price_bars_for_tickers(
        [row.ticker for row in rows], start_date=date.today() - timedelta(days=14)
    )
    positions = [{
        "ticker": row.ticker, "name": row.name or row.ticker,
        "pnl_pct": round((row.current_price / row.entry_price - 1) * 100, 1) if row.entry_price else 0,
        "has_stop": row.stop_price is not None,
    } for row in rows]
    currencies = {str(row.currency or "").upper() for row in rows}
    pairs: list[tuple[Any, Any, Any]] = []
    for row in rows:
        bars = _deduplicated_price_bars(prices_by_ticker.get(row.ticker.upper(), []))
        if len(bars) >= 2:
            pairs.append((row, bars[-2], bars[-1]))

    daily_status, daily_change, daily_as_of = "missing", None, None
    if rows and len(currencies) > 1:
        daily_status = "mixed_currency"
    elif rows and len(pairs) != len(rows):
        daily_status = "partial"
    elif pairs:
        latest_dates = {latest.date for _row, _previous, latest in pairs}
        previous_dates = {previous.date for _row, previous, _latest in pairs}
        if len(latest_dates) != 1 or len(previous_dates) != 1:
            daily_status = "partial"
        else:
            previous_total = sum(float(row.shares) * float(previous.close) for row, previous, _latest in pairs)
            current_total = sum(float(row.shares) * float(latest.close) for row, _previous, latest in pairs)
            daily_change = round((current_total / previous_total - 1) * 100, 2) if previous_total else None
            daily_as_of = next(iter(latest_dates)).isoformat()
            daily_status = "available" if daily_change is not None else "missing"
    return {
        "positions_count": len(positions),
        "stop_coverage_count": sum(item["has_stop"] for item in positions),
        "stop_coverage_total": len(positions),
        "daily_price_change_pct": daily_change,
        "daily_price_change_as_of": daily_as_of,
        "daily_price_change_status": daily_status,
        "comparable_positions": len(pairs),
        "tickers": [row.ticker for row in rows],
        "positions": sorted(positions, key=lambda item: item["pnl_pct"])[:5],
    }


def _sell_sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        {"Verkaufen": 0, "Beobachten": 1, "Halten": 2}.get(row.get("status"), 3),
        0 if row.get("data_quality_status") == "blocked" else 1,
        -int(row.get("recommendation_pct") or 0),
    )


def _priority_rows(
    sell_rows: list[dict[str, Any]], earnings: dict[str, date],
    opportunity_rows: list[dict[str, Any]], watchlist: set[str],
) -> tuple[list[dict[str, Any]], int]:
    priorities: dict[str, dict[str, Any]] = {}
    review_tickers: set[str] = set()
    for row in sell_rows:
        if row.get("status") == "Halten" and row.get("data_quality_status") == "trusted":
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        review_tickers.add(ticker)
        blocked = row.get("data_quality_status") != "trusted"
        priorities[ticker] = {
            "ticker": ticker,
            "category": "Datenqualität / Depot" if blocked else "Depot / Verkaufssignal",
            "label": "Daten prüfen" if row.get("data_quality_status") == "blocked" else row.get("status", "Beobachten"),
            "detail": row.get("data_quality_detail") if blocked else row.get("primary_signal") or row.get("reason") or "Im Verkaufsmonitor prüfen.",
            "href": f"/sell-monitor/{ticker}",
            "tone": "bad" if row.get("status") == "Verkaufen" or row.get("data_quality_status") == "blocked" else "warning",
            "priority": 0 if row.get("status") == "Verkaufen" else 1 if blocked else 2,
        }
    for raw_ticker, earnings_date in earnings.items():
        ticker = str(raw_ticker).upper()
        days_until = (earnings_date - date.today()).days
        if not 0 <= days_until <= 7:
            continue
        detail = "Earnings heute" if days_until == 0 else f"Earnings in {days_until} Tagen"
        existing = priorities.get(ticker)
        if existing:
            existing["category"] = f"{existing['category']} · Earnings"
            existing["detail"] = f"{existing['detail']} · {detail}"
            continue
        priorities[ticker] = {
            "ticker": ticker, "category": "Depot / Earnings", "label": "Earnings bald", "detail": detail,
            "href": f"/stocks/{ticker}", "tone": "warning", "priority": 3,
        }
    for row in opportunity_rows:
        ticker = str(row.get("ticker") or "").upper()
        changes = list(row.get("positive_changes") or [])
        if not ticker or not changes or ticker in priorities:
            continue
        priorities[ticker] = {
            "ticker": ticker,
            "category": "Watchlist / Veränderung" if ticker in watchlist else "Top Aktien / Veränderung",
            "label": "Setup verbessert", "detail": " · ".join(changes[:2]),
            "href": f"/stocks/{ticker}", "tone": "good", "priority": 4,
        }
    result = sorted(priorities.values(), key=lambda row: (row["priority"], row["ticker"]))
    for row in result:
        row.pop("priority", None)
    return result, len(review_tickers)


def _change_details(row: dict[str, Any]) -> list[str]:
    details: list[str] = []
    for field, label, digits in (
        ("overall_score_delta", "Gesamtscore", 0),
        ("technical_score_delta", "Technik", 1),
        ("rs_rating_delta", "RS", 0),
    ):
        value = row.get(field)
        if isinstance(value, (int, float)) and value:
            details.append(f"{label} {value:+.{digits}f}")
    details.extend(change for change in row.get("positive_changes", []) if str(change).startswith("Neu:") and change not in details)
    return details[:3]


def _home_changes(*, portfolio_tickers: set[str], watchlist: set[str]) -> list[dict[str, Any]]:
    source = daily_opportunities.get_home_changes(priority_tickers=sorted(portfolio_tickers | watchlist), limit=12)
    if not source.get("previous_as_of"):
        return []
    rows: list[dict[str, Any]] = []
    for row in source.get("rows", []):
        ticker = str(row.get("ticker") or "").upper()
        details = _change_details(row)
        if not ticker or not details:
            continue
        scopes = [scope for scope, contains in (
            ("portfolio", ticker in portfolio_tickers),
            ("watchlist", ticker in watchlist),
            ("top_stocks", row.get("rank") is not None and row.get("rank") <= 3),
        ) if contains]
        if not scopes:
            continue
        rows.append({
            "ticker": ticker, "scopes": scopes,
            "kind": "signal" if any(detail.startswith("Neu:") for detail in details) else "score",
            "summary": " · ".join(details[:2]), "details": details,
            "as_of": source.get("as_of"), "previous_as_of": source.get("previous_as_of"),
            "href": f"/stocks/{ticker}",
        })
    scope_priority = {"portfolio": 0, "watchlist": 1, "top_stocks": 2}
    return sorted(rows, key=lambda row: (min(scope_priority[scope] for scope in row["scopes"]), row["ticker"]))[:8]


def _watchlist_rows(tickers: list[str], assessments: list[Any], *, failed: bool) -> list[dict[str, Any]]:
    by_ticker = {row.ticker.upper(): row for row in assessments}
    rows = []
    for ticker in tickers:
        snapshot = by_ticker.get(ticker)
        if snapshot is None:
            rows.append({"ticker": ticker, "name": ticker, "data_status": "error" if failed else "missing"})
        else:
            rows.append(snapshot.item_json | {
                "ticker": ticker, "name": snapshot.name or ticker,
                "as_of": snapshot.as_of.isoformat(), "data_status": "available",
            })
    return rows


def get_home_dashboard() -> dict[str, Any]:
    errors: list[str] = []
    workspace = _read("workspace", get_workspace_state, errors, None)
    market = _read("market", _market_summary, errors, {"indices": []})
    quality = _read("data_quality", get_data_quality_summary, errors, None)
    opportunities = _read("opportunities", daily_opportunities.get_top_daily, errors, {"rows": [], "status": "not_ready"})
    portfolio = _read("portfolio", _portfolio_summary, errors, {"positions_count": 0, "positions": [], "tickers": []})

    def stored_sell_rows() -> list[dict[str, Any]]:
        rows, _generated_at, _job_id = sell_state_repository.list_ranking_snapshot()
        return [row.model_dump(mode="json") for row in rows]

    sell_rows = _read("sell", stored_sell_rows, errors, [])
    sell_rows.sort(key=_sell_sort_key)
    all_watchlist = [str(item).upper() for item in getattr(workspace, "watchlist", []) if str(item).strip()]
    shown_watchlist = all_watchlist[:8]
    assessments = _read("watchlist_assessments", lambda: stock_assessments.list_all_snapshots(shown_watchlist), errors, [])
    group_as_of, groups = _read(
        "industry_groups",
        lambda: industry_group_repository.list_home_rankings(
            taxonomy_version=TAXONOMY_VERSION, algorithm_version=ALGORITHM_VERSION, limit=5,
        ),
        errors, (None, []),
    )
    opportunity_rows = list(opportunities.get("rows", []))[:3]
    portfolio_tickers = {str(ticker).upper() for ticker in portfolio.get("tickers", [])}
    watchlist_set = set(all_watchlist)
    earnings = _read("earnings", lambda: earnings_repository.next_earnings_dates(sorted(portfolio_tickers)), errors, {})
    priorities, review_positions_count = _priority_rows(sell_rows, earnings, opportunity_rows, watchlist_set)
    changes = _read("changes", lambda: _home_changes(portfolio_tickers=portfolio_tickers, watchlist=watchlist_set), errors, [])
    return {
        "generated_at": datetime.now(UTC).isoformat(), "as_of": market.get("as_of"),
        "data_quality": quality, "errors": errors, "market": market,
        "priorities": priorities[:7], "priorities_total": len(priorities),
        "review_positions_count": review_positions_count,
        "opportunities": opportunity_rows, "changes": changes, "portfolio": portfolio,
        "sell_rows": sell_rows[:12], "industry_groups": groups,
        "industry_groups_as_of": group_as_of.isoformat() if group_as_of else None,
        "watchlist": _watchlist_rows(shown_watchlist, assessments, failed="watchlist_assessments" in errors),
        "watchlist_total": len(all_watchlist),
    }
