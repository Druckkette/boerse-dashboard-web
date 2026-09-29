"""Read-only, persisted-data aggregation for the investor home dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from app.repositories import portfolio as portfolio_repository
from app.repositories import sell_state as sell_state_repository
from app.repositories import stock_assessments
from app.services import daily_opportunities, industry_group_rs
from app.services.market import get_breadth, get_market_overview, get_volatility
from app.services.settings import get_data_quality_summary
from app.services.workspace import get_workspace_state


def _read(label: str, callback: Callable[[], Any], errors: list[str], default: Any) -> Any:
    try:
        return callback()
    except Exception:  # noqa: BLE001 - one unavailable card must not break home
        errors.append(label)
        return default


def _portfolio_summary() -> dict[str, Any]:
    rows = portfolio_repository.list_open_positions()
    positions = [
        {
            "ticker": row.ticker,
            "name": row.name or row.ticker,
            "pnl_pct": round((row.current_price / row.entry_price - 1) * 100, 1) if row.entry_price else 0,
            "has_stop": row.stop_price is not None,
        }
        for row in rows
    ]
    return {
        "positions_count": len(positions),
        "stop_coverage_count": sum(item["has_stop"] for item in positions),
        "stop_coverage_total": len(positions),
        "positions": positions[:5],
    }


def get_home_dashboard() -> dict[str, Any]:
    errors: list[str] = []
    workspace = _read("workspace", get_workspace_state, errors, None)
    market = _read("market", lambda: get_market_overview(ticker="^GSPC"), errors, None)
    nasdaq = _read("nasdaq", lambda: get_market_overview(ticker="^IXIC"), errors, None)
    breadth = _read("breadth", get_breadth, errors, None)
    volatility = _read("volatility", get_volatility, errors, None)
    quality = _read("data_quality", get_data_quality_summary, errors, None)
    opportunities = _read("opportunities", daily_opportunities.get_top_daily, errors, {"rows": [], "status": "not_ready"})
    portfolio = _read("portfolio", _portfolio_summary, errors, {"positions_count": 0, "positions": []})

    def stored_sell_rows() -> list[dict[str, Any]]:
        rows, _generated_at, _job_id = sell_state_repository.list_ranking_snapshot()
        return [row.model_dump(mode="json") for row in rows]

    sell_rows = _read("sell", stored_sell_rows, errors, [])
    groups = _read("industry_groups", lambda: industry_group_rs.list_rankings(include_small=False), errors, {"rows": [], "as_of": None})

    watchlist = list(getattr(workspace, "watchlist", []) if workspace else [])[:8]
    watch_rows = _read(
        "watchlist_assessments",
        lambda: [row.item_json | {"ticker": row.ticker, "name": row.name, "as_of": row.as_of.isoformat()} for row in stock_assessments.list_all_snapshots(watchlist)],
        errors,
        [],
    )

    opportunity_rows = opportunities.get("rows", [])[:3]
    priority_rows = []
    for row in sell_rows:
        if row.get("status") != "Halten" or row.get("data_quality_status") != "trusted":
            priority_rows.append({
                "ticker": row.get("ticker", ""),
                "label": "Daten prüfen" if row.get("data_quality_status") == "blocked" else row.get("status", "Beobachten"),
                "detail": row.get("data_quality_detail") if row.get("data_quality_status") != "trusted" else row.get("primary_signal") or row.get("reason", ""),
                "href": f"/sell-monitor/{row.get('ticker', '')}",
                "tone": "bad" if row.get("status") == "Verkaufen" or row.get("data_quality_status") == "blocked" else "warning",
            })
    for row in opportunity_rows:
        if row.get("positive_changes"):
            priority_rows.append({
                "ticker": row.get("ticker", ""), "label": "Setup verbessert",
                "detail": " · ".join(row.get("positive_changes", [])[:2]),
                "href": f"/stocks/{row.get('ticker', '')}", "tone": "good",
            })

    latest_breadth = (getattr(breadth, "points", []) or [])[-1] if breadth else None
    latest_volatility = (getattr(volatility, "points", []) or [])[-1] if volatility else None
    market_payload = market.model_dump(mode="json") if market else None
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": getattr(market, "as_of", None),
        "data_quality": quality,
        "errors": errors,
        "market": {
            "overview": market_payload,
            "nasdaq": nasdaq.model_dump(mode="json") if nasdaq else None,
            "breadth": latest_breadth.model_dump(mode="json") if latest_breadth else None,
            "volatility": latest_volatility.model_dump(mode="json") if latest_volatility else None,
        },
        "priorities": priority_rows[:7],
        "opportunities": opportunity_rows,
        "changes": [
            {"ticker": row.get("ticker", ""), "detail": detail, "href": f"/stocks/{row.get('ticker', '')}"}
            for row in opportunity_rows
            for detail in (row.get("positive_changes", [])[:2] or row.get("warnings", [])[:1])
        ][:8],
        "portfolio": portfolio,
        "sell_rows": sell_rows[:8],
        "industry_groups": sorted(groups.get("rows", []), key=lambda row: row.get("rank") or 999)[:5],
        "watchlist": watch_rows[:8],
    }
