from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from typing import Any

from app.repositories import trade_journal as repository
from app.schemas import TradeJournalChartMarker, TradeJournalChartPoint, TradeJournalHistoricalChart
from app.services.fx import yahoo_quote_currency
from app.services.market_calendar import previous_us_market_session_date


def historical_chart(row: Any, executions: list[Any], stock: dict) -> TradeJournalHistoricalChart:
    """Daily bars stop at the selected execution; scores retain their earlier cutoff."""
    markers = [TradeJournalChartMarker(
        entry_id=item.id, date=item.trade_date.isoformat(), entry_type=item.entry_type,
        price=item.price, currency=item.currency or "EUR", shares=item.shares, selected=item.id == row.id,
    ) for item in executions if item.entry_type in {"buy", "sell"} and item.trade_date <= row.trade_date]
    # FIFO may refer to a buy imported before this position was grouped.
    for allocation in (row.portfolio_snapshot_json or {}).get("allocations", []):
        buy_date = allocation.get("buy_date")
        if buy_date and buy_date <= row.trade_date.isoformat() and not any(
            marker.entry_type == "buy" and marker.date == buy_date for marker in markers
        ):
            markers.append(TradeJournalChartMarker(date=buy_date, entry_type="buy", shares=allocation.get("shares")))
    first_buy = min((date.fromisoformat(marker.date) for marker in markers if marker.entry_type == "buy"),
                    default=row.trade_date)
    display_start = min(row.trade_date - timedelta(days=186), first_buy - timedelta(days=30))
    bars = repository.historical_price_bars(
        row.ticker, start_date=display_start - timedelta(days=1200), end_date=row.trade_date,
    )
    # Defensive cutoff and de-duplication also prevent a second data source from
    # counting the same session twice in the moving averages.
    by_date = {}
    for bar in bars:
        if bar.date <= row.trade_date and bar.close is not None and isfinite(bar.close):
            by_date.setdefault(bar.date, bar)
    closes: list[float] = []
    ema21 = None
    points = []
    for day, bar in sorted(by_date.items()):
        close = float(bar.close)
        closes.append(close)
        ema21 = close if ema21 is None else close * (2 / 22) + ema21 * (1 - 2 / 22)
        if day < display_start:
            continue
        points.append(TradeJournalChartPoint(
            date=day.isoformat(), open=bar.open, high=bar.high, low=bar.low, close=close,
            adj_close=bar.adj_close, volume=bar.volume, ema21=ema21,
            sma10=_average(closes, 10), sma50=_average(closes, 50), sma200=_average(closes, 200),
        ))
    assessment_day = previous_us_market_session_date(row.trade_date)
    # A stale snapshot must never move the pre-execution chart beyond the last
    # complete session, even for legacy/manual snapshots made after the trade.
    snapshot_date = str(stock.get("data_as_of") or stock.get("assessment", {}).get("as_of") or "")[:10]
    if snapshot_date:
        try:
            assessment_day = min(assessment_day, date.fromisoformat(snapshot_date))
        except ValueError:
            pass
    return TradeJournalHistoricalChart(
        currency=yahoo_quote_currency(row.ticker), execution_date=row.trade_date.isoformat(),
        assessment_as_of=assessment_day.isoformat(),
        first_date=points[0].date if points else None, last_date=points[-1].date if points else None,
        points=points, markers=sorted(markers, key=lambda marker: (marker.date, marker.entry_type, marker.entry_id)),
    )


def _average(closes: list[float], sessions: int) -> float | None:
    return sum(closes[-sessions:]) / sessions if len(closes) >= sessions else None
