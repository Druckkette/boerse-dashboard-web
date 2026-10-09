"""Small read-only aggregation for the investor home dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.domain.market.ampel import AMPEL_RULESET_VERSION
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
from app.services.market_calendar import completed_us_market_session, daily_bar_is_final, expected_us_market_session
from app.services.market import _market_trend_ampel_for_ticker, _selected_market_ampel_logic
from app.services.settings import get_data_quality_summary
from app.services.workspace import get_workspace_state


_HOME_CACHE_TTL_SECONDS = 30.0
_home_cache: tuple[float, str, dict[str, Any]] | None = None
_home_cache_lock = Lock()


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
        "gelb_rally_unter_druck": "Rally unter Druck", "neutral": "Neutral",
    }.get(phase or "", "Nicht verfügbar")


def _index_summary(ticker: str, label: str, points: list[Any] | None = None) -> dict[str, Any]:
    """Build a daily index comparison from two canonical persisted closes."""
    completed = completed_us_market_session()
    points = [
        point for point in (points if points is not None else market_repository.load_latest_close_pair(ticker))
        if daily_bar_is_final(point.date, point.fetched_at)
    ][-2:]
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
    logic = _selected_market_ampel_logic()
    breadth_rows = market_repository.list_breadth_daily(DEFAULT_MARKET_UNIVERSE_KEY, limit=1)
    breadth = breadth_rows[-1] if breadth_rows else None
    closes_by_ticker = market_repository.load_latest_close_pairs(["^VIX", "^GSPC", "^IXIC", "^RUT"])
    vix = _index_summary("^VIX", "VIX", closes_by_ticker.get("^VIX", []))
    indices = []
    for ticker, label in (("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq Composite"), ("^RUT", "Russell 2000")):
        item = _index_summary(ticker, label, closes_by_ticker.get(ticker, []))
        try:
            trend = _market_trend_ampel_for_ticker(ticker, lookback_days=550, logic=logic)
        except Exception:  # noqa: BLE001 - retain the other indices if one source fails
            trend = None
        item.update({
            "phase": trend.phase if trend else None,
            "phase_label": _phase_label(trend.phase if trend else None),
            "phase_as_of": trend.as_of if trend else None,
            "phase_status": (
                "missing" if trend is None else "stale" if trend.as_of != completed.date.isoformat()
                else "partial" if not trend.price_data_complete else "available"
            ),
            "phase_reason": trend.phase_reason if trend else None,
            "previous_phase": getattr(trend, "previous_phase", None),
            "previous_phase_label": _phase_label(getattr(trend, "previous_phase", None)),
            "previous_phase_as_of": getattr(trend, "previous_phase_as_of", None),
            "powertrend": {
                "enabled": logic == "ibd",
                "state": trend.powertrend_state,
                "formal_active": trend.powertrend_formally_active,
                "start_date": trend.powertrend_start_date,
                "pressure_since": trend.powertrend_pressure_since,
            } if trend else None,
        })
        indices.append(item)
    current_indices = [item for item in indices if item["phase_status"] == "available"]
    phases = {item["phase"] for item in current_indices}
    complete = len(current_indices) == len(indices)
    phase = (next(iter(phases)) if len(phases) == 1 else "mixed") if complete else None
    phase_label = "Uneinheitlich" if phase == "mixed" else _phase_label(phase) if complete else "Marktstand unvollständig"
    summary = " · ".join(f"{item['label']}: {item['phase_label']}" for item in current_indices)
    if not complete:
        summary = f"{len(current_indices)} von {len(indices)} Index-Ampeln aktuell. " + summary
    return {
        "session": {
            "phase": "open" if expected.phase == "intraday" else "closed" if expected.phase == "closed" else "unknown",
            "last_completed_as_of": completed.date.isoformat(),
            "current_session_as_of": expected.date.isoformat(),
        },
        "logic": logic,
        "phase": phase,
        "phase_label": phase_label,
        "summary": summary,
        "status": "available" if complete else "partial" if current_indices else "missing",
        "breadth": {
            "as_of": breadth.date.isoformat(),
            "pct_above_50sma": breadth.pct_above_50sma,
        } if breadth else None,
        "volatility": {
            "as_of": vix.get("as_of"), "close": vix.get("close"), "status": vix.get("status"),
        },
        "indices": indices,
        "as_of": completed.date.isoformat() if current_indices else None,
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
        "positions": sorted(positions, key=lambda item: item["pnl_pct"]),
    }


def _sell_sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        {"Verkaufen": 0, "Beobachten": 1, "Halten": 2}.get(row.get("status"), 3),
        0 if row.get("data_quality_status") == "blocked" else 1,
        -int(row.get("recommendation_pct") or 0),
    )


def _portfolio_alerts(sell_rows: list[dict[str, Any]], portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    """Present stored decisions; never promote pending/unreliable signals to sells."""
    completed = completed_us_market_session().date.isoformat()
    alerts = []
    covered = set()
    for row in sell_rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        covered.add(ticker)
        seen = str(row.get("last_seen_date") or "")
        generated = row.get("generated_at")
        try:
            generated_time = datetime.fromisoformat(str(generated).replace("Z", "+00:00")) if generated else None
            if generated_time and generated_time.tzinfo is None:
                generated_time = generated_time.replace(tzinfo=UTC)
            generated_current = bool(generated_time and generated_time.date().isoformat() >= completed and generated_time <= datetime.now(UTC))
        except ValueError:
            generated_current = False
        stale = not seen or seen < completed or seen > expected_us_market_session().date.isoformat() or not generated_current
        unreliable = row.get("data_quality_status") != "trusted"
        pending = row.get("pending_status")
        action = row.get("status") == "Verkaufen" and pending == "scharf" and (row.get("recommendation_pct") or 0) > 0
        if stale or unreliable:
            category, label, tone = "data", "Daten prüfen", "warning"
            reason = row.get("data_quality_detail") or "Bewertung nicht ausreichend verlässlich."
            if stale:
                reason = "Verkaufsmonitor nicht aktuell oder Bewertungszeitpunkt fehlt. " + (row.get("data_quality_detail") or "")
        elif action:
            category, label, tone = "action", "Verkaufen", "bad"
            reason = row.get("primary_signal") or row.get("reason") or "Bestätigtes Verkaufssignal."
        elif row.get("status") != "Halten" or pending in {"in_bestaetigung", "snoozed"}:
            category, label, tone = "observe", "Beobachten", "warning"
            reason = row.get("primary_signal") or row.get("reason") or "Signal im Verkaufsmonitor prüfen."
            if pending == "in_bestaetigung":
                reason = "Bestätigung ausstehend · " + reason
            elif pending == "snoozed":
                reason = "Signal zurückgestellt bis " + (row.get("snoozed_until") or "unbekannt") + " · " + reason
        else:
            continue
        alerts.append({
            "id": f"sell:{ticker}", "ticker": ticker, "name": row.get("name") or ticker,
            "category": category, "label": label, "tone": tone, "detail": reason.strip(),
            "signal": row.get("primary_signal") or row.get("reason") or "Kein auswertbares Signal",
            "recommendation_pct": row.get("recommendation_pct") if category == "action" else None,
            "pending_status": pending, "data_quality_status": row.get("data_quality_status"),
            "last_seen_date": seen or None, "generated_at": generated,
            "freshness": "stale" if stale else "current", "href": f"/sell-monitor/{ticker}",
        })
    for ticker in sorted(set(portfolio.get("tickers", [])) - covered):
        alerts.append({"id": f"missing:{ticker}", "ticker": ticker, "category": "data",
                       "label": "Daten prüfen", "tone": "warning", "detail": "Keine gespeicherte Verkaufsbewertung vorhanden.",
                       "href": f"/sell-monitor/{ticker}", "freshness": "missing"})
    for position in portfolio.get("positions", []):
        if not position.get("has_stop"):
            ticker = position["ticker"]
            alerts.append({"id": f"stop:{ticker}", "ticker": ticker, "category": "observe",
                           "label": "Stop fehlt", "tone": "warning", "detail": "Für diese Position ist kein Stop hinterlegt.",
                           "href": f"/sell-monitor/{ticker}"})
    return sorted(alerts, key=lambda row: ({"action": 0, "observe": 1, "data": 2}[row["category"]], -(row.get("recommendation_pct") or 0), row["ticker"], row["id"]))


def _earnings_calendar(portfolio: dict[str, Any], watchlist: set[str], assessment_names: dict[str, str] | None = None) -> dict[str, Any]:
    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    depot = set(portfolio.get("tickers", []))
    names = {**(assessment_names or {}), **{row["ticker"]: row["name"] for row in portfolio.get("positions", [])}}
    rows = earnings_repository.upcoming_earnings_events(sorted(depot | watchlist), start_date=today, end_date=today + timedelta(days=29))
    for row in rows:
        row["name"] = names.get(row["ticker"], row["ticker"])
        row["scopes"] = [scope for scope, members in (("portfolio", depot), ("watchlist", watchlist)) if row["ticker"] in members]
        row["days_until"] = (date.fromisoformat(row["date"]) - today).days
        row["href"] = f"/stocks/{row['ticker']}"
    return {"today": today.isoformat(), "rows": rows, "status": "available",
            "missing_portfolio_count": len(depot - {row["ticker"] for row in rows})}


def _home_changes(*, portfolio_tickers: set[str], watchlist: set[str]) -> list[dict[str, Any]]:
    source = daily_opportunities.get_home_changes(priority_tickers=sorted(portfolio_tickers | watchlist))
    rows = []
    for row in source.get("rows", []):
        ticker = row["ticker"]
        scopes = [scope for scope, contains in (
            ("portfolio", ticker in portfolio_tickers), ("watchlist", ticker in watchlist),
            ("top_stocks", row.get("rank") is not None and row["rank"] <= 3),
        ) if contains]
        if scopes:
            if row.get("new_candidate") and "watchlist" in scopes:
                row = {**row, "summary": "Neue Watchlist-Chance"}
            rows.append({**row, "scopes": scopes, "as_of": source.get("as_of"),
                         "previous_as_of": source.get("previous_as_of"), "href": f"/stocks/{ticker}"})
    return sorted(rows, key=lambda row: (0 if "portfolio" in row["scopes"] else 1 if "watchlist" in row["scopes"] else 2, row["ticker"]))


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
    # Monitor snapshots can predate an import or sale: portfolio membership is authoritative.
    open_tickers = {str(ticker).strip().upper() for ticker in portfolio.get("tickers", [])}
    sell_rows = [row for row in sell_rows if str(row.get("ticker") or "").strip().upper() in open_tickers]
    sell_rows.sort(key=_sell_sort_key)
    all_watchlist = [str(item).upper() for item in getattr(workspace, "watchlist", []) if str(item).strip()]
    shown_watchlist = all_watchlist
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
    earnings = _read("earnings", lambda: _earnings_calendar(portfolio, watchlist_set, {row.ticker: row.name for row in assessments}), errors, {"rows": [], "status": "error"})
    alerts = _portfolio_alerts(sell_rows, portfolio)
    review_positions_count = len({row["ticker"] for row in alerts})
    changes = _read("changes", lambda: _home_changes(portfolio_tickers=portfolio_tickers, watchlist=watchlist_set), errors, [])
    return {
        "schema_version": 2, "generated_at": datetime.now(UTC).isoformat(), "as_of": market.get("as_of"),
        "data_quality": quality, "errors": errors, "market": market,
        "portfolio_alerts": alerts, "earnings": earnings,
        "priorities": alerts, "priorities_total": len(alerts),
        "review_positions_count": review_positions_count,
        "opportunities": opportunity_rows, "changes": changes, "portfolio": portfolio,
        "sell_rows": sell_rows, "industry_groups": groups,
        "industry_groups_as_of": group_as_of.isoformat() if group_as_of else None,
        "watchlist": _watchlist_rows(shown_watchlist, assessments, failed="watchlist_assessments" in errors),
        "watchlist_total": len(all_watchlist),
    }


def invalidate_home_dashboard_cache() -> None:
    global _home_cache
    with _home_cache_lock:
        _home_cache = None


def get_cached_home_dashboard() -> dict[str, Any]:
    """Serve a very short-lived snapshot so the home route stays responsive.

    All values are persisted dashboard data.  A 30-second cache avoids repeated
    database aggregation on navigation while keeping newly stored snapshots
    visible almost immediately.  It never triggers external data retrieval.
    """
    global _home_cache
    now = monotonic()
    logic = _selected_market_ampel_logic()
    with _home_cache_lock:
        if _home_cache and _home_cache[1] == f"{logic}:{AMPEL_RULESET_VERSION}" and now - _home_cache[0] < _HOME_CACHE_TTL_SECONDS:
            return _home_cache[2]
        payload = get_home_dashboard()
        _home_cache = (now, f"{logic}:{AMPEL_RULESET_VERSION}", payload)
        return payload


def warm_home_dashboard_cache() -> None:
    """Precompute the small home payload before the API starts serving traffic."""
    get_cached_home_dashboard()
