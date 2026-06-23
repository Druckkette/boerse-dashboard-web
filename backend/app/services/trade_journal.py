from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.repositories import trade_journal as journal_repository
from app.repositories.trade_journal import TradeJournalRepositoryUnavailable
from app.schemas import (
    TradeJournalDefaultsResponse,
    TradeJournalEntriesResponse,
    TradeJournalEntryDetail,
    TradeJournalEntryRequest,
    TradeJournalEntryResponse,
    TradeJournalEntrySummary,
    TradeJournalImageSet,
)
from app.services.fx import get_eur_usd_rate
from app.services.market import get_market_ampel, get_market_overview
from app.services.portfolio import get_portfolio_positions, get_portfolio_snapshot
from app.services.prices import get_price_history
from app.services.relative_strength import get_relative_strength_for_ticker
from app.services.sec13f import get_institutional_13f_for_ticker
from app.services.stocks import get_stock_assessment, get_stock_fundamentals


IMAGE_DATA_URL_LIMIT = 2_500_000


def get_trade_journal_entries(ticker: str | None = None) -> TradeJournalEntriesResponse:
    clean = _clean_ticker(ticker) if ticker else None
    rows = journal_repository.list_entries(clean)
    return TradeJournalEntriesResponse(ticker=clean, entries=[_summary_from_row(row) for row in rows])


def get_trade_journal_entry(entry_id: str) -> TradeJournalEntryResponse:
    row = journal_repository.get_entry(entry_id)
    if row is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
    return TradeJournalEntryResponse(entry=_detail_from_row(row))


def get_trade_journal_defaults(ticker: str, entry_type: str) -> TradeJournalDefaultsResponse:
    clean = _clean_ticker(ticker)
    clean_type = _clean_entry_type(entry_type)
    price = _current_price(clean)
    portfolio_snapshot = _portfolio_context(clean, price=price, shares=None)
    market_snapshot = _market_snapshot()
    if clean_type == "sell":
        open_buy = journal_repository.latest_open_buy_entry(clean)
    elif clean_type == "ex_post":
        open_buy = journal_repository.latest_closed_buy_entry(clean)
    else:
        open_buy = None
    stop_price = float(open_buy.stop_price) if open_buy is not None and open_buy.stop_price is not None else None
    return TradeJournalDefaultsResponse(
        ticker=clean,
        entry_type=clean_type,
        trade_date=date.today().isoformat(),
        price=price,
        shares=float(open_buy.shares) if open_buy is not None and open_buy.shares is not None else None,
        open_buy_entry_id=open_buy.id if open_buy is not None else None,
        open_buy_price=float(open_buy.price) if open_buy is not None and open_buy.price is not None else None,
        open_buy_date=open_buy.trade_date.isoformat() if open_buy is not None else None,
        stop_price=stop_price,
        stop_distance_pct=_stop_distance_pct(price, stop_price),
        portfolio_snapshot=portfolio_snapshot,
        market_snapshot=market_snapshot,
    )


def create_trade_journal_entry(payload: TradeJournalEntryRequest) -> TradeJournalEntryResponse:
    clean = _clean_ticker(payload.ticker)
    entry_type = _clean_entry_type(payload.entry_type)
    _validate_images(payload.chart_images)

    trade_date = payload.trade_date or date.today()
    price = _finite(payload.price) or _current_price(clean)
    shares = _finite(payload.shares)
    linked_buy = _linked_buy(clean, payload.linked_entry_id) if entry_type in {"sell", "ex_post"} else None
    linked_entry_id = payload.linked_entry_id or (linked_buy.id if linked_buy is not None else None)
    realized_pnl_eur, realized_pnl_pct = _realized_pnl(linked_buy, price=price, shares=shares)
    stop_deviation_pct = _stop_deviation(linked_buy, price=price)
    status = _default_status(entry_type, payload.status, payload.close_with_related_buy)

    values = {
        "ticker": clean,
        "entry_type": entry_type,
        "status": status,
        "trade_date": trade_date,
        "price": price,
        "shares": shares,
        "stop_price": _finite(payload.stop_price),
        "stop_distance_pct": _stop_distance_pct(price, payload.stop_price),
        "linked_entry_id": linked_entry_id,
        "realized_pnl_eur": realized_pnl_eur,
        "realized_pnl_pct": realized_pnl_pct,
        "stop_deviation_pct": stop_deviation_pct,
        "basis_text": payload.basis_text.strip(),
        "alternative_entry": payload.alternative_entry,
        "alternative_entry_text": payload.alternative_entry_text.strip(),
        "primary_reasons": payload.primary_reasons.strip(),
        "sell_reason": payload.sell_reason.strip(),
        "questionnaire_json": payload.questionnaire,
        "stock_snapshot_json": _stock_snapshot(clean),
        "market_snapshot_json": _market_snapshot(),
        "portfolio_snapshot_json": _portfolio_context(clean, price=price, shares=shares),
        "chart_images_json": payload.chart_images.model_dump(),
    }
    row = journal_repository.create_entry(values)
    if payload.close_with_related_buy and linked_entry_id:
        journal_repository.close_related_entries([row.id, linked_entry_id])
        row = journal_repository.get_entry(row.id) or row
    return TradeJournalEntryResponse(entry=_detail_from_row(row))


def update_trade_journal_entry(entry_id: str, payload: TradeJournalEntryRequest) -> TradeJournalEntryResponse:
    existing = journal_repository.get_entry(entry_id)
    if existing is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")

    clean = _clean_ticker(payload.ticker)
    entry_type = _clean_entry_type(payload.entry_type)
    _validate_images(payload.chart_images)
    price = _finite(payload.price)
    shares = _finite(payload.shares)
    linked_buy = _linked_buy(clean, payload.linked_entry_id or existing.linked_entry_id) if entry_type in {"sell", "ex_post"} else None
    realized_pnl_eur, realized_pnl_pct = _realized_pnl(linked_buy, price=price, shares=shares)
    stop_deviation_pct = _stop_deviation(linked_buy, price=price)

    values = {
        "ticker": clean,
        "entry_type": entry_type,
        "status": _default_status(entry_type, payload.status, payload.close_with_related_buy),
        "trade_date": payload.trade_date or existing.trade_date,
        "price": price,
        "shares": shares,
        "stop_price": _finite(payload.stop_price),
        "stop_distance_pct": _stop_distance_pct(price, payload.stop_price),
        "linked_entry_id": payload.linked_entry_id or existing.linked_entry_id,
        "realized_pnl_eur": realized_pnl_eur,
        "realized_pnl_pct": realized_pnl_pct,
        "stop_deviation_pct": stop_deviation_pct,
        "basis_text": payload.basis_text.strip(),
        "alternative_entry": payload.alternative_entry,
        "alternative_entry_text": payload.alternative_entry_text.strip(),
        "primary_reasons": payload.primary_reasons.strip(),
        "sell_reason": payload.sell_reason.strip(),
        "questionnaire_json": payload.questionnaire,
        "portfolio_snapshot_json": _portfolio_context(clean, price=price, shares=shares),
        "chart_images_json": payload.chart_images.model_dump(),
    }
    row = journal_repository.update_entry(entry_id, values)
    if row is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
    if payload.close_with_related_buy and row.linked_entry_id:
        journal_repository.close_related_entries([row.id, row.linked_entry_id])
        row = journal_repository.get_entry(row.id) or row
    return TradeJournalEntryResponse(entry=_detail_from_row(row))


def close_trade_journal_entry(entry_id: str) -> TradeJournalEntryResponse:
    row = journal_repository.close_entry(entry_id)
    if row is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
    return TradeJournalEntryResponse(entry=_detail_from_row(row))


def _clean_ticker(ticker: str | None) -> str:
    clean = (ticker or "").strip().upper()
    if not clean:
        raise ValueError("Ticker ist erforderlich.")
    return clean


def _clean_entry_type(entry_type: str) -> str:
    clean = entry_type.strip().lower()
    if clean not in {"buy", "sell", "ex_post"}:
        raise ValueError("entry_type muss buy, sell oder ex_post sein.")
    return clean


def _current_price(ticker: str) -> float | None:
    try:
        assessment = get_stock_assessment(ticker)
    except Exception:
        return None
    return _finite(assessment.metrics.last_close)


def _stock_snapshot(ticker: str) -> dict:
    snapshot: dict[str, Any] = {"ticker": ticker, "snapshot_schema": "stock_detail_v2"}
    try:
        assessment = get_stock_assessment(ticker).model_dump(mode="json")
        snapshot["assessment"] = assessment
        # Keep the original flat shape for older UI/tests that read stock_snapshot.checks directly.
        snapshot.update({key: value for key, value in assessment.items() if key not in snapshot})
    except Exception as exc:
        snapshot["assessment"] = {"ticker": ticker, "source": "missing", "error": f"{type(exc).__name__}: {exc}"}

    try:
        snapshot["fundamentals"] = get_stock_fundamentals(ticker).model_dump(mode="json")
    except Exception as exc:
        snapshot["fundamentals"] = {"ticker": ticker, "source": "missing", "error": f"{type(exc).__name__}: {exc}"}

    try:
        snapshot["institutional_13f"] = get_institutional_13f_for_ticker(ticker).model_dump(mode="json")
    except Exception as exc:
        snapshot["institutional_13f"] = {"ticker": ticker, "source": "missing", "error": f"{type(exc).__name__}: {exc}"}

    try:
        price_history = get_price_history(ticker, range_key="1y").model_dump(mode="json")
        points = price_history.get("points") if isinstance(price_history.get("points"), list) else []
        snapshot["price_history"] = {**price_history, "points": points[-260:]}
    except Exception as exc:
        snapshot["price_history"] = {"ticker": ticker, "source": "missing", "error": f"{type(exc).__name__}: {exc}"}

    try:
        snapshot["relative_strength"] = get_relative_strength_for_ticker(ticker).model_dump(mode="json")
    except Exception as exc:
        snapshot["relative_strength"] = {"ticker": ticker, "source": "missing", "error": f"{type(exc).__name__}: {exc}"}
    return snapshot


def _market_snapshot() -> dict:
    snapshot: dict[str, Any] = {}
    try:
        overview = get_market_overview(ticker="^GSPC")
        snapshot["overview"] = overview.model_dump(mode="json")
    except Exception as exc:
        snapshot["overview"] = {"source": "missing", "error": f"{type(exc).__name__}: {exc}"}

    try:
        ampel = get_market_ampel(ticker="SPY", days=90)
        latest = ampel.chart_points[-1] if ampel.chart_points else None
        ma_behavior = {}
        if latest is not None:
            close = _finite(latest.close)
            ema21 = _finite(latest.ema21)
            sma50 = _finite(latest.sma50)
            sma200 = _finite(latest.sma200)
            ma_behavior = {
                "close": close,
                "ema21": ema21,
                "sma50": sma50,
                "sma200": sma200,
                "above_ema21": close is not None and ema21 is not None and close > ema21,
                "above_sma50": close is not None and sma50 is not None and close > sma50,
                "above_sma200": close is not None and sma200 is not None and close > sma200,
                "correct_order": (
                    ema21 is not None
                    and sma50 is not None
                    and sma200 is not None
                    and ema21 > sma50 > sma200
                ),
            }
        snapshot["ampel"] = {
            "ticker": ampel.ticker,
            "as_of": ampel.as_of,
            "phase": ampel.phase_info.phase,
            "phase_label": ampel.phase_info.label,
            "warning_count": ampel.warning_count,
            "ma_behavior": ma_behavior,
        }
    except Exception as exc:
        snapshot["ampel"] = {"source": "missing", "error": f"{type(exc).__name__}: {exc}"}
    return snapshot


def _portfolio_context(ticker: str, *, price: float | None, shares: float | None) -> dict:
    context: dict[str, Any] = {
        "ticker": ticker,
        "price_usd": price,
        "shares": shares,
        "position_size_usd": None,
        "position_size_eur": None,
        "weight_pct": None,
        "atr_pct": None,
        "beta": None,
        "beta_balancer_score": None,
        "risk_contribution": None,
        "fx_rate": None,
    }
    price_value = _finite(price)
    shares_value = _finite(shares)
    if price_value is not None and shares_value is not None:
        context["position_size_usd"] = round(price_value * shares_value, 2)
        try:
            fx_rate = get_eur_usd_rate()
            context["fx_rate"] = {"rate": fx_rate.rate, "as_of": fx_rate.as_of.isoformat(), "source": fx_rate.source}
            if fx_rate.rate > 0:
                context["position_size_eur"] = round(context["position_size_usd"] / fx_rate.rate, 2)
        except Exception:
            context["position_size_eur"] = None

    try:
        snapshot = get_portfolio_snapshot()
        context["portfolio_total_value"] = snapshot.total_value
        context["portfolio_currency_hint"] = _portfolio_currency_hint(snapshot)
    except Exception as exc:
        context["portfolio_error"] = f"{type(exc).__name__}: {exc}"
        snapshot = None

    try:
        positions = get_portfolio_positions()
    except Exception:
        positions = []
    position = next((item for item in positions if item.ticker.upper() == ticker), None)
    if position is not None:
        context.update(
            {
                "weight_pct": position.weight_pct,
                "atr_pct": position.atr_pct,
                "beta": position.beta,
                "beta_balancer_score": position.beta_balancer_score,
                "risk_contribution": position.risk_contribution,
                "stop_price": position.stop_price,
            }
        )
    elif snapshot is not None and context["position_size_usd"] is not None and snapshot.total_value:
        context["weight_pct"] = round(context["position_size_usd"] / snapshot.total_value * 100, 2)

    if context["atr_pct"] is None or context["beta"] is None:
        try:
            metrics = get_stock_assessment(ticker).metrics
            context["atr_pct"] = context["atr_pct"] if context["atr_pct"] is not None else metrics.atr_pct
            context["beta"] = context["beta"] if context["beta"] is not None else metrics.beta
        except Exception:
            pass
    return context


def _portfolio_currency_hint(snapshot: Any) -> str:
    if getattr(snapshot, "positions", None):
        first = snapshot.positions[0]
        return getattr(first, "currency", "") or ""
    return ""


def _linked_buy(ticker: str, linked_entry_id: str | None):
    if linked_entry_id:
        row = journal_repository.get_entry(linked_entry_id)
        if row is not None:
            return row
    return journal_repository.latest_open_buy_entry(ticker)


def _realized_pnl(linked_buy: Any, *, price: float | None, shares: float | None) -> tuple[float | None, float | None]:
    buy_price = _finite(getattr(linked_buy, "price", None))
    sell_price = _finite(price)
    clean_shares = _finite(shares) or _finite(getattr(linked_buy, "shares", None))
    if buy_price is None or sell_price is None:
        return None, None
    pnl_pct = round((sell_price / buy_price - 1) * 100, 2) if buy_price else None
    if clean_shares is None:
        return None, pnl_pct
    pnl_usd = (sell_price - buy_price) * clean_shares
    try:
        rate = get_eur_usd_rate().rate
        pnl_eur = round(pnl_usd / rate, 2) if rate else round(pnl_usd, 2)
    except Exception:
        pnl_eur = round(pnl_usd, 2)
    return pnl_eur, pnl_pct


def _stop_deviation(linked_buy: Any, *, price: float | None) -> float | None:
    stop_price = _finite(getattr(linked_buy, "stop_price", None))
    current = _finite(price)
    if stop_price is None or current is None or stop_price <= 0:
        return None
    return round((current / stop_price - 1) * 100, 2)


def _stop_distance_pct(price: float | None, stop_price: float | None) -> float | None:
    current = _finite(price)
    stop = _finite(stop_price)
    if current is None or stop is None or current <= 0:
        return None
    return round((current - stop) / current * 100, 2)


def _default_status(entry_type: str, requested: str | None, close_with_related_buy: bool) -> str:
    if requested in {"open", "closed", "draft"}:
        return requested
    if close_with_related_buy or entry_type in {"sell", "ex_post"}:
        return "closed"
    return "open"


def _validate_images(images: TradeJournalImageSet) -> None:
    for label, value in images.model_dump().items():
        if value and len(value) > IMAGE_DATA_URL_LIMIT:
            raise ValueError(f"{label} ist zu groß. Bitte ein komprimiertes Bild unter ca. 2 MB hochladen.")


def _summary_from_row(row: Any) -> TradeJournalEntrySummary:
    return TradeJournalEntrySummary(
        id=row.id,
        ticker=row.ticker,
        entry_type=row.entry_type,
        status=row.status,
        trade_date=row.trade_date.isoformat(),
        price=row.price,
        shares=row.shares,
        realized_pnl_eur=row.realized_pnl_eur,
        realized_pnl_pct=row.realized_pnl_pct,
        linked_entry_id=row.linked_entry_id,
        title=_entry_title(row),
        summary=_entry_summary(row),
        created_at=_iso_datetime(row.created_at),
        updated_at=_iso_datetime(row.updated_at),
    )


def _detail_from_row(row: Any) -> TradeJournalEntryDetail:
    summary = _summary_from_row(row)
    images = row.chart_images_json or {}
    return TradeJournalEntryDetail(
        **summary.model_dump(),
        stop_price=row.stop_price,
        stop_distance_pct=row.stop_distance_pct,
        stop_deviation_pct=row.stop_deviation_pct,
        basis_text=row.basis_text or "",
        alternative_entry=bool(row.alternative_entry),
        alternative_entry_text=row.alternative_entry_text or "",
        primary_reasons=row.primary_reasons or "",
        sell_reason=row.sell_reason or "",
        questionnaire=row.questionnaire_json or {},
        stock_snapshot=row.stock_snapshot_json or {},
        market_snapshot=row.market_snapshot_json or {},
        portfolio_snapshot=row.portfolio_snapshot_json or {},
        chart_images=TradeJournalImageSet(
            daily_chart=str(images.get("daily_chart") or ""),
            weekly_chart=str(images.get("weekly_chart") or ""),
        ),
    )


def _entry_title(row: Any) -> str:
    label = {"buy": "Kauf", "sell": "Verkauf", "ex_post": "Ex-Post Analyse"}.get(row.entry_type, row.entry_type)
    return f"{label} {row.ticker} · {row.trade_date.isoformat()}"


def _entry_summary(row: Any) -> str:
    price = f"{row.price:.2f} USD" if row.price is not None else "Preis offen"
    shares = f"{row.shares:g} Stk." if row.shares is not None else "Stückzahl offen"
    if row.entry_type == "sell" and row.realized_pnl_pct is not None:
        return f"{shares} zu {price} · P&L {row.realized_pnl_pct:+.1f}%"
    return f"{shares} zu {price}"


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        clean = float(value)
    except (TypeError, ValueError):
        return None
    if clean != clean or clean in {float("inf"), float("-inf")}:
        return None
    return clean


def _iso_datetime(value: datetime | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    return value.isoformat()


__all__ = [
    "TradeJournalRepositoryUnavailable",
    "close_trade_journal_entry",
    "create_trade_journal_entry",
    "get_trade_journal_defaults",
    "get_trade_journal_entries",
    "get_trade_journal_entry",
    "update_trade_journal_entry",
]
