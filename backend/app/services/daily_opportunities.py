"""A fast research shortlist from persisted assessments, not a second stock engine.

Dynamics has a neutral midpoint of 50. Its six weighted components are score
delta (25%), technical delta (15%), configured RS delta (20%), SPY-relative
1/5-session returns (15%), price-confirmed volume (10%), and newly gained or
lost assessment/chart signals (15%). Missing comparisons stay neutral rather
than manufacturing yesterday's values. Quality retains 65% by default.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import isfinite

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core_config import get_settings
from app.db.models import DailyStockOpportunity, Instrument, PriceBar
from app.db.session import SessionLocal
from app.repositories import stock_assessments, portfolio
from app.services.workspace import get_workspace_state
from app.services.market_calendar import expected_us_market_session, price_is_current, previous_us_market_session_date, daily_bar_is_final, completed_us_market_session


COMPONENT_WEIGHTS = {
    "overall": 0.25, "technical": 0.15, "rs": 0.20,
    "relative": 0.15, "volume": 0.10, "signals": 0.15,
}


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _number(value) -> float | None:
    try:
        number = float(value) if value is not None else None
        return number if number is not None and isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _signals(item: dict) -> list[str]:
    checks = item.get("checks") or []
    passed = [str(check["label"]) for check in checks if isinstance(check, dict)
              and check.get("passed") and check.get("category") in {"technical", "trend"}]
    chart = [f"Chart: {label}" for label in item.get("positive_signals") or []]
    return sorted(set(passed + chart))


def _relative_returns(ticker_bars: list[tuple], spy_bars: list[tuple], day: date) -> tuple[float | None, float | None, float | None]:
    stock = {bar[0]: bar[1] for bar in ticker_bars if bar[1] and bar[1] > 0 and bar[0] <= day}
    spy = {bar[0]: bar[1] for bar in spy_bars if bar[1] and bar[1] > 0 and bar[0] <= day}
    dates = sorted(set(stock) & set(spy))
    if not dates or dates[-1] != day:
        return None, None, None
    one = ((stock[day] / stock[dates[-2]] - spy[day] / spy[dates[-2]]) * 100) if len(dates) >= 2 else None
    five = ((stock[day] / stock[dates[-6]] - spy[day] / spy[dates[-6]]) * 100) if len(dates) >= 6 else None
    stock_day = (stock[day] / stock[dates[-2]] - 1) * 100 if len(dates) >= 2 else None
    return one, five, stock_day


def calculate_daily_rows(
    items: list[dict], previous: dict[str, dict], bars: dict[str, list[tuple]],
    *, day: date, quality_weight: float = 0.65, min_quality: int = 70,
    min_rs: int = 80, min_fundamental: float = 50, min_trend: float = 50,
    min_price: float = 15, min_dollar_volume_mio: float = 30,
    require_fresh_price: bool = True,
) -> list[dict]:
    """Pure ranking core. Bars are only recent cached (day, close, fetched_at)."""
    if not 0 <= quality_weight <= 1:
        raise ValueError("quality_weight must be between 0 and 1")
    rows = []
    spy = bars.get("SPY", [])
    for item in items:
        if item.get("as_of") != day.isoformat():
            continue
        ticker = str(item["ticker"])
        old = previous.get(ticker)
        now_signals = _signals(item)
        old_signals = set(old.get("signals_json") or []) if old else set()
        score = _number(item.get("overall_score")) or 0
        technical = _number(item.get("technical_score")) or 0
        rs = _number(item.get("rs_rating"))
        close = _number(item.get("last_close"))
        liquidity = _number(item.get("dollar_volume_mio"))
        latest = bars.get(ticker, [])
        current_bar = next((bar for bar in reversed(latest) if bar[0] == day), None)
        fresh = bool(current_bar and (not require_fresh_price or price_is_current(day, current_bar[2])))
        qualified = (fresh and (item.get("overall_status") or "available") == "available"
                     and score >= min_quality and rs is not None and rs >= min_rs
                     and (_number(item.get("fundamental_score")) or 0) >= min_fundamental
                     and (_number(item.get("moving_average_score")) or 0) >= min_trend
                     and close is not None and close >= min_price
                     and liquidity is not None and liquidity >= min_dollar_volume_mio
                     and item.get("fundamentals_available") is True
                     and item.get("rs_line_available") is True)
        details = {}
        dynamics = opportunity = None
        if qualified:
            overall_delta = score - (_number(old.get("overall_score")) or 0) if old else None
            technical_delta = technical - (_number(old.get("technical_score")) or 0) if old else None
            old_rs = _number(old.get("rs_rating")) if old else None
            rs_delta = rs - old_rs if old_rs is not None else None
            rel_1d, rel_5d, stock_day = _relative_returns(latest, spy, day)
            ratio = _number(item.get("volume_ratio_50d"))
            new_signals = sorted(set(now_signals) - old_signals) if old else []
            lost_signals = sorted(old_signals - set(now_signals)) if old else []
            relative_component = 50 + (rel_1d or 0) * 5 + (rel_5d or 0) * 3
            volume_component = 50
            if ratio is not None and stock_day is not None:
                volume_component += max(-2, min(3, ratio - 1)) * (20 if stock_day > 0 else -20)
            components = {
                "overall": _clamp(50 + (overall_delta or 0) * 8),
                "technical": _clamp(50 + (technical_delta or 0) * 5),
                "rs": _clamp(50 + (rs_delta or 0) * 6),
                "relative": _clamp(relative_component),
                "volume": _clamp(volume_component),
                "signals": _clamp(50 + 12 * len(new_signals) - 12 * len(lost_signals)),
            }
            dynamics = round(sum(components[key] * weight for key, weight in COMPONENT_WEIGHTS.items()), 1)
            opportunity = round(score * quality_weight + dynamics * (1 - quality_weight), 1)
            changes = []
            if overall_delta and overall_delta > 0:
                changes.append(f"Gesamtscore {overall_delta:+.0f}")
            if technical_delta and technical_delta > 0:
                changes.append(f"Technischer Score {technical_delta:+.1f}")
            if rs_delta and rs_delta > 0:
                changes.append(f"RS {old_rs:.0f} → {rs:.0f}")
            changes.extend(f"Neu: {signal}" for signal in new_signals[:3])
            if rel_5d is not None and rel_5d > 0:
                changes.append(f"5T vs. SPY {rel_5d:+.1f} %")
            reasons = changes[:5]
            factual_reasons = [
                f"RS-Rating {rs:.0f}",
                f"Trend-Score {float(item['moving_average_score']):.0f}",
                f"Fundamental-Score {float(item['fundamental_score']):.0f}",
                f"Gesamtscore {score:.0f}",
            ]
            if ratio is not None and ratio >= 1.2 and stock_day is not None and stock_day > 0:
                factual_reasons.insert(0, f"Volumen {ratio:.1f}× 50T bei positivem Kurstag")
            for reason in factual_reasons:
                if len(reasons) >= 3:
                    break
                reasons.append(reason)
            warnings = []
            earnings = item.get("next_earnings_date")
            if earnings:
                try:
                    days_to_earnings = (date.fromisoformat(earnings) - day).days
                    if 0 <= days_to_earnings <= 7:
                        warnings.append(f"Earnings in {days_to_earnings} Kalendertagen")
                except ValueError:
                    pass
            if item.get("top_warning"):
                warnings.append(str(item["top_warning"]))
            if rs_delta is not None and rs_delta <= -5:
                warnings.append(f"RS-Rating {rs_delta:+.0f} seit dem letzten Snapshot")
            if lost_signals:
                warnings.append(f"Signal verloren: {lost_signals[0]}")
            if not old:
                warnings.append("Noch keine historische Score-Vergleichsbasis")
            details = {
                "name": item.get("name") or ticker, "last_close": close,
                "overall_score_delta": overall_delta, "technical_score_delta": technical_delta,
                "rs_rating_delta": rs_delta, "relative_performance_1d": round(rel_1d, 2) if rel_1d is not None else None,
                "relative_performance_5d": round(rel_5d, 2) if rel_5d is not None else None,
                "volume_ratio": ratio, "dollar_volume_mio": liquidity,
                "positive_changes": changes[:5], "reasons": reasons[:5], "warnings": warnings[:4],
                "components": {key: round(value, 1) for key, value in components.items()},
                "previous_rank": old.get("rank") if old else None,
            }
        # Comparison metadata also belongs to weak tracked stocks. Never turn
        # an unavailable assessment or unfinished candle into a lost signal.
        comparison_valid = bool(old and fresh and daily_bar_is_final(day, current_bar[2])
                                and (item.get("overall_status") or "available") == "available"
                                and old.get("comparison_available", True))
        details.update({
            "history_version": 2, "name": item.get("name") or ticker,
            "comparison_available": fresh and bool(current_bar and daily_bar_is_final(day, current_bar[2]))
                                    and (item.get("overall_status") or "available") == "available",
            "previous_overall_score": old.get("overall_score") if comparison_valid else None,
            "previous_rs_rating": old.get("rs_rating") if comparison_valid else None,
            "overall_score_delta": score - old["overall_score"] if comparison_valid else None,
            "rs_rating_delta": rs - old["rs_rating"] if comparison_valid and rs is not None and old.get("rs_rating") is not None else None,
            "new_signals": sorted(set(now_signals) - old_signals) if comparison_valid else [],
            "lost_signals": sorted(old_signals - set(now_signals)) if comparison_valid else [],
            "candidate_qualified": qualified,
            "previous_candidate_qualified": old.get("candidate_qualified") if comparison_valid else None,
        })
        rows.append({
            "as_of": day, "ticker": ticker, "overall_score": int(score),
            "technical_score": technical, "fundamental_score": _number(item.get("fundamental_score")) or 0,
            "moving_average_score": _number(item.get("moving_average_score")) or 0,
            "chart_behavior_score": int(_number(item.get("chart_behavior_score")) or 0),
            "rs_rating": int(rs) if rs is not None else None, "signals_json": now_signals,
            "daily_dynamics_score": dynamics, "daily_opportunity_score": opportunity,
            "rank": None, "details_json": details,
        })
    ranked = sorted((row for row in rows if row["daily_opportunity_score"] is not None),
                    key=lambda row: (-row["daily_opportunity_score"], -row["overall_score"], row["ticker"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return rows


def refresh_top_daily(writes=None) -> dict:
    """Persist research candidates and all tracked stocks in the same daily history."""
    day = expected_us_market_session().date
    source = writes if writes is not None else stock_assessments.list_all_snapshots()
    settings = get_settings()
    tracked = set(get_workspace_state().watchlist) | {row.ticker for row in portfolio.list_open_positions()}
    # Partial screening writes must not erase already assessed tracked stocks.
    by_ticker = {row.ticker: row for row in source}
    missing_tracked = sorted(tracked - set(by_ticker))
    if writes is not None and missing_tracked:
        for row in stock_assessments.list_all_snapshots(missing_tracked):
            by_ticker.setdefault(row.ticker, row)
    items = [row.item_json for row in by_ticker.values() if row.as_of == day
             and (row.ticker in tracked or ((row.item_json.get("overall_status") or "available") == "available"
                  and row.overall_score >= max(0, settings.daily_min_quality - 20)))]
    candidate_tickers = [item["ticker"] for item in items if item.get("overall_score", 0) >= settings.daily_min_quality or item["ticker"] in tracked]
    with SessionLocal() as db:
        prior_day = previous_us_market_session_date(day)
        previous = {}
        if prior_day:
            previous = {row.ticker: {
                "overall_score": row.overall_score, "technical_score": row.technical_score,
                "rs_rating": row.rs_rating, "rank": row.rank, "signals_json": row.signals_json,
                "comparison_available": (row.details_json or {}).get("comparison_available", bool(row.details_json)),
                "candidate_qualified": (row.details_json or {}).get("candidate_qualified"),
            } for row in db.scalars(select(DailyStockOpportunity).where(DailyStockOpportunity.as_of == prior_day))}
        bars: dict[str, list[tuple]] = defaultdict(list)
        if candidate_tickers:
            # About 14 calendar days x the prefiltered candidates, never full OHLC histories.
            price_rows = db.execute(select(Instrument.ticker, PriceBar.date, PriceBar.close, PriceBar.fetched_at)
                                    .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                                    .where(Instrument.ticker.in_(candidate_tickers + ["SPY"]),
                                           PriceBar.date.between(day - timedelta(days=14), day),
                                           PriceBar.close.is_not(None))
                                    .order_by(Instrument.ticker, PriceBar.date, PriceBar.fetched_at)).all()
            by_date: dict[str, dict[date, tuple]] = defaultdict(dict)
            for ticker, bar_day, close, fetched_at in price_rows:
                by_date[ticker][bar_day] = (bar_day, close, fetched_at)
            bars = {ticker: sorted(days.values()) for ticker, days in by_date.items()}
        rows = calculate_daily_rows(
            items, previous, bars, day=day, quality_weight=settings.daily_quality_weight,
            min_quality=settings.daily_min_quality, min_rs=settings.daily_min_rs,
            min_fundamental=settings.daily_min_fundamental, min_trend=settings.daily_min_trend,
            min_price=settings.daily_min_price, min_dollar_volume_mio=settings.daily_min_dollar_volume_mio,
        )
        # Transactional same-day replacement prevents removed/stale tickers from
        # retaining yesterday's rank, while preserving all earlier sessions.
        db.execute(delete(DailyStockOpportunity).where(DailyStockOpportunity.as_of == day))
        for offset in range(0, len(rows), 500):
            batch = rows[offset:offset + 500]
            db.execute(insert(DailyStockOpportunity).values(batch))
        db.commit()
    return {"as_of": day.isoformat(), "assessed_count": len(rows),
            "qualified_count": sum(row["rank"] is not None for row in rows),
            "previous_as_of": prior_day.isoformat() if prior_day else None}


def get_top_daily() -> dict:
    """Read only three indexed history rows; never start a background job on GET."""
    expected = expected_us_market_session().date
    with SessionLocal() as db:
        day = db.scalar(select(func.max(DailyStockOpportunity.as_of)))
        if day is None:
            return {"as_of": None, "generated_at": None, "status": "not_ready", "rows": []}
        rows = db.scalars(select(DailyStockOpportunity)
                          .where(DailyStockOpportunity.as_of == day, DailyStockOpportunity.rank <= 3)
                          .order_by(DailyStockOpportunity.rank)).all()
        return {"as_of": day.isoformat(), "generated_at": max((row.generated_at for row in rows), default=None),
                "status": "current" if day == expected else "stale", "rows": [
                    {"rank": row.rank, "ticker": row.ticker,
                     "daily_opportunity_score": row.daily_opportunity_score,
                     "quality_score": row.overall_score,
                     "daily_dynamics_score": row.daily_dynamics_score,
                     "overall_score": row.overall_score, "technical_score": row.technical_score,
                     "fundamental_score": row.fundamental_score,
                     "moving_average_score": row.moving_average_score,
                     "chart_behavior_score": row.chart_behavior_score,
                     "rs_rating": row.rs_rating, **row.details_json}
                    for row in rows]}


HOME_CHANGE_THRESHOLD = 5


def _relevant_home_change(row, old) -> dict | None:
    """Compare actual consecutive session rows, including pre-v2 saved history."""
    current = row.details_json or {}
    previous = old.details_json or {} if old else {}
    if old is None or not current.get("comparison_available", bool(current)) or not previous.get("comparison_available", bool(previous)):
        return None
    details = []
    for field, label, threshold in (("overall_score", "Score", 75), ("rs_rating", "RS", 80)):
        before, after = getattr(old, field), getattr(row, field)
        if before is not None and after is not None and (abs(after - before) >= HOME_CHANGE_THRESHOLD or (before < threshold) != (after < threshold)):
            details.append(f"{label} {before:g} → {after:g}")
    gained = sorted(set(row.signals_json or []) - set(old.signals_json or []))
    lost = sorted(set(old.signals_json or []) - set(row.signals_json or []))
    details.extend(f"Neu: {signal}" for signal in gained)
    details.extend(f"Entfallen: {signal}" for signal in lost)
    new_candidate = current.get("candidate_qualified") is True and previous.get("candidate_qualified") is False
    lost_candidate = current.get("candidate_qualified") is False and previous.get("candidate_qualified") is True
    if new_candidate:
        details.insert(0, "Tagesauswahl-Kriterien erstmals erfüllt")
    if lost_candidate:
        details.insert(0, "Tagesauswahl-Kriterien nicht mehr erfüllt")
    if not details:
        return None
    negative = lost_candidate or bool(lost) or row.overall_score < old.overall_score or (row.rs_rating is not None and old.rs_rating is not None and row.rs_rating < old.rs_rating)
    return {"ticker": row.ticker, "rank": row.rank, "name": current.get("name") or row.ticker,
            "kind": "signal" if gained or lost or new_candidate or lost_candidate else "score",
            "summary": "Stärke verloren" if negative else "Bewertung verbessert",
            "details": details, "tone": "warning" if negative else "good", "new_candidate": new_candidate}


def get_home_changes(*, priority_tickers: list[str], limit: int | None = None) -> dict:
    """Batched persisted comparison; no universe scan or positive-only truncation."""
    clean = sorted({ticker.strip().upper() for ticker in priority_tickers if ticker.strip()})
    with SessionLocal() as db:
        day = db.scalar(select(func.max(DailyStockOpportunity.as_of)).where(DailyStockOpportunity.as_of <= completed_us_market_session().date))
        if day is None:
            return {"as_of": None, "previous_as_of": None, "rows": []}
        previous_day = previous_us_market_session_date(day)
        rows = db.scalars(select(DailyStockOpportunity).where(
            DailyStockOpportunity.as_of == day,
            or_(DailyStockOpportunity.ticker.in_(clean), DailyStockOpportunity.rank <= 3),
        ).order_by(DailyStockOpportunity.ticker)).all()
        old = {row.ticker: row for row in db.scalars(select(DailyStockOpportunity).where(
            DailyStockOpportunity.as_of == previous_day, DailyStockOpportunity.ticker.in_([row.ticker for row in rows]),
        ))} if rows else {}
        changed = [change for row in rows if (change := _relevant_home_change(row, old.get(row.ticker))) is not None]
    return {"as_of": day.isoformat(), "previous_as_of": previous_day.isoformat(),
            "rows": changed if limit is None else changed[:max(1, int(limit))]}
