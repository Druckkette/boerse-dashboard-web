from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.domain.market.ampel import AMPEL_RULESET_VERSION
from app.repositories import trade_journal as journal_repository
from app.repositories.trade_journal import TradeJournalRepositoryUnavailable
from app.schemas import (
    TradeJournalAnalyticsResponse,
    TradeJournalCoverageBlock,
    TradeJournalCoverageResponse,
    TradeJournalDefaultsResponse,
    TradeJournalEntriesResponse,
    TradeJournalEntryDetail,
    TradeJournalNoteRequest,
    TradeJournalEntryRequest,
    TradeJournalEntryResponse,
    TradeJournalEntrySummary,
    TradeJournalTradeSummary,
    TradeJournalTradesResponse,
    TradeJournalImageSet,
)
from app.services.fx import get_eur_usd_rate
from app.services.market import get_market_ampel, get_market_overview
from app.services.portfolio import get_portfolio_positions, get_portfolio_snapshot
from app.services.prices import get_price_history
from app.services.relative_strength import get_relative_strength_for_ticker
from app.services.sec13f import get_institutional_13f_for_ticker
from app.services.stocks import get_stock_assessment, get_stock_fundamentals
from app.services.trade_journal_chart import historical_chart


IMAGE_DATA_URL_LIMIT = 2_500_000


def get_trade_journal_entries(
    ticker: str | None = None,
    *,
    query: str | None = None,
    entry_type: str | None = None,
    status: str | None = None,
    source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "newest",
) -> TradeJournalEntriesResponse:
    clean = _clean_ticker(ticker) if ticker else None
    rows, total = journal_repository.list_entries(
        clean,
        query=query,
        entry_type=entry_type,
        status=status,
        source=source,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    next_offset = offset + len(rows) if offset + len(rows) < total else None
    return TradeJournalEntriesResponse(
        ticker=clean,
        entries=[_summary_from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
    )


def get_trade_journal_trades(
    *, query: str | None = None, date_from: date | None = None, date_to: date | None = None
) -> TradeJournalTradesResponse:
    rows = journal_repository.list_trade_entries(query=query, date_from=date_from, date_to=date_to)
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        # Position IDs survive prepended broker history and are therefore the stable public trade ID.
        key = row.position_id or row.trade_group_id or row.linked_entry_id or row.id
        grouped.setdefault(key, []).append(row)
    trades = [_trade_summary(key, group) for key, group in grouped.items()]
    trades.sort(key=lambda item: (item.first_entry_date, item.id), reverse=True)
    return TradeJournalTradesResponse(trades=trades, total=len(trades))


def get_trade_journal_trade(trade_id: str) -> TradeJournalTradeSummary:
    response = get_trade_journal_trades()
    trade = next((item for item in response.trades if item.id == trade_id), None)
    if trade is None:
        raise ValueError("Trade wurde nicht gefunden.")
    return trade


def get_trade_journal_analytics(
    *, query: str | None = None, date_from: date | None = None, date_to: date | None = None
) -> TradeJournalAnalyticsResponse:
    trades = get_trade_journal_trades(query=query, date_from=date_from, date_to=date_to).trades
    closed = [item for item in trades if item.status == "closed" and item.realized_pnl is not None]
    winners = [item.realized_pnl for item in closed if (item.realized_pnl or 0) > 0]
    losers = [item.realized_pnl for item in closed if (item.realized_pnl or 0) < 0]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    return TradeJournalAnalyticsResponse(
        closed_trades=len(closed),
        net_result=sum(item.realized_pnl or 0 for item in closed),
        winners=len(winners),
        losers=len(losers),
        hit_rate_pct=round(len(winners) / len(closed) * 100, 2) if closed else None,
        average_win=round(gross_profit / len(winners), 2) if winners else None,
        average_loss=round(sum(losers) / len(losers), 2) if losers else None,
        profit_factor=round(gross_profit / gross_loss, 2) if gross_loss else None,
        excluded_incomplete=sum(1 for item in trades if item.status == "closed" and item.realized_pnl is None),
    )


def get_trade_journal_coverage() -> TradeJournalCoverageResponse:
    return TradeJournalCoverageResponse(
        generated_at=datetime.now(UTC).isoformat(),
        blocks=[TradeJournalCoverageBlock(**item) for item in journal_repository.coverage_summary()],
    )


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
        "currency": payload.currency.strip().upper(),
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
        "stock_snapshot_json": _manual_snapshot_context(_stock_snapshot(clean), trade_date),
        "market_snapshot_json": _manual_snapshot_context(_market_snapshot(), trade_date),
        "portfolio_snapshot_json": {
            **_portfolio_context(clean, price=price, shares=shares),
            "source": "manual",
            "fees": _finite(payload.fees),
            "tax": _finite(payload.tax),
            "source_evidence": payload.source_evidence.strip(),
        },
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

    imported = bool(getattr(existing, "source_transaction_id", None))
    clean = existing.ticker if imported else _clean_ticker(payload.ticker)
    entry_type = existing.entry_type if imported else _clean_entry_type(payload.entry_type)
    _validate_images(payload.chart_images)
    price = existing.price if imported else _finite(payload.price)
    shares = existing.shares if imported else _finite(payload.shares)
    linked_buy = _linked_buy(clean, payload.linked_entry_id or existing.linked_entry_id) if entry_type in {"sell", "ex_post"} and not imported else None
    realized_pnl_eur, realized_pnl_pct = _realized_pnl(linked_buy, price=price, shares=shares)
    stop_deviation_pct = _stop_deviation(linked_buy, price=price)

    values = {
        "ticker": clean,
        "entry_type": entry_type,
        "currency": existing.currency if imported else payload.currency.strip().upper(),
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
        "portfolio_snapshot_json": {} if imported else {
            **(existing.portfolio_snapshot_json or {}),
            **_portfolio_context(clean, price=price, shares=shares),
            "source": "manual",
            "fees": _finite(payload.fees),
            "tax": _finite(payload.tax),
            "source_evidence": payload.source_evidence.strip(),
        },
        "chart_images_json": payload.chart_images.model_dump(),
    }
    if getattr(existing, "source_transaction_id", None):
        # Broker executions and FIFO results remain authoritative when editing notes.
        for key in ("ticker", "entry_type", "currency", "status", "trade_date", "price", "shares",
                    "linked_entry_id", "realized_pnl_eur", "realized_pnl_pct", "portfolio_snapshot_json"):
            values.pop(key, None)
    row = journal_repository.update_entry(entry_id, values)
    if row is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
    if payload.close_with_related_buy and row.linked_entry_id and not getattr(row, "source_transaction_id", None):
        journal_repository.close_related_entries([row.id, row.linked_entry_id])
        row = journal_repository.get_entry(row.id) or row
    return TradeJournalEntryResponse(entry=_detail_from_row(row))


def update_trade_journal_notes(entry_id: str, payload: TradeJournalNoteRequest) -> TradeJournalEntryResponse:
    existing = journal_repository.get_entry(entry_id)
    if existing is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
    _validate_images(payload.chart_images)
    row = journal_repository.update_notes(entry_id, {
        "basis_text": payload.basis_text.strip(),
        "alternative_entry": payload.alternative_entry,
        "alternative_entry_text": payload.alternative_entry_text.strip(),
        "primary_reasons": payload.primary_reasons.strip(),
        "sell_reason": payload.sell_reason.strip(),
        "questionnaire_json": payload.questionnaire,
        "chart_images_json": payload.chart_images.model_dump(),
    })
    if row is None:
        raise ValueError("Tagebucheintrag wurde nicht gefunden.")
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


def _manual_snapshot_context(snapshot: dict, trade_date: date) -> dict:
    captured_at = datetime.now(UTC).isoformat()
    is_backdated = trade_date < date.today()
    return {
        **snapshot,
        "context_status": "partial" if is_backdated else "archived",
        "generated_at": captured_at,
        "captured_at": captured_at,
        "trade_date": trade_date.isoformat(),
        "information_cutoff": None if is_backdated else captured_at,
        "temporal_reliability": "unverified_backfill" if is_backdated else "captured_at_entry",
        "context_notice": (
            "Beim Nachtrag erfasste aktuelle Daten; kein Beleg fuer den damaligen Informationsstand."
            if is_backdated else
            "Beim Speichern erfasster Datenstand."
        ),
    }


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
            "logic": ampel.logic,
            "ruleset_version": AMPEL_RULESET_VERSION,
            "ftd_negated": ampel.cycle.ftd_negated,
            "ftd_intraday_undercut": ampel.cycle.ftd_intraday_undercut,
            "startschuss_date": ampel.cycle.startschuss_date,
            "powertrend": ampel.powertrend.model_dump(mode="json"),
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
    metadata = journal_repository.execution_metadata(
        getattr(row, "source_transaction_id", None), row.ticker
    )
    contexts = journal_repository.latest_contexts(row.id)
    context_status, context_label = _context_status(row, contexts)
    portfolio = row.portfolio_snapshot_json or {}
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
        currency=getattr(row, "currency", "USD") or "USD",
        realized_pnl=getattr(row, "realized_pnl", None),
        source_transaction_id=getattr(row, "source_transaction_id", None),
        trade_group_id=getattr(row, "trade_group_id", None),
        position_id=getattr(row, "position_id", None),
        instrument_name=metadata["instrument_name"],
        isin=metadata["isin"],
        execution_at=metadata["execution_at"],
        source="trade_republic" if getattr(row, "source_transaction_id", None) else "manual",
        fees=metadata["fees"] if metadata["fees"] is not None else _finite(portfolio.get("fees")),
        tax=metadata["tax"] if metadata["tax"] is not None else _finite(portfolio.get("tax")),
        gross_amount=metadata["gross_amount"],
        net_amount=metadata["net_amount"],
        context_status=context_status,
        context_label=context_label,
        has_note=_has_note(row),
        title=_entry_title(row),
        summary=_entry_summary(row),
        created_at=_iso_datetime(row.created_at),
        updated_at=_iso_datetime(row.updated_at),
    )


def _detail_from_row(row: Any) -> TradeJournalEntryDetail:
    summary = _summary_from_row(row)
    images = row.chart_images_json or {}
    contexts = journal_repository.latest_contexts(row.id)
    stock_snapshot = contexts.get("stock").payload_json if contexts.get("stock") else row.stock_snapshot_json or {}
    market_snapshot = contexts.get("market").payload_json if contexts.get("market") else row.market_snapshot_json or {}
    executions = journal_repository.related_entries(row)
    return TradeJournalEntryDetail(
        **summary.model_dump(),
        executions=[_summary_from_row(item) for item in executions],
        historical_chart=historical_chart(row, executions, stock_snapshot),
        sell_assessment=getattr(row, "sell_assessment_json", {}) or {},
        stop_price=row.stop_price,
        stop_distance_pct=row.stop_distance_pct,
        stop_deviation_pct=row.stop_deviation_pct,
        basis_text=row.basis_text or "",
        alternative_entry=bool(row.alternative_entry),
        alternative_entry_text=row.alternative_entry_text or "",
        primary_reasons=row.primary_reasons or "",
        sell_reason=row.sell_reason or "",
        questionnaire=row.questionnaire_json or {},
        stock_snapshot=stock_snapshot,
        market_snapshot=market_snapshot,
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
    currency = getattr(row, "currency", "USD") or "USD"
    price = f"{row.price:.2f} {currency}" if row.price is not None else "Preis offen"
    shares = f"{row.shares:g} Stk." if row.shares is not None else "Stückzahl offen"
    if row.entry_type == "sell" and row.realized_pnl_pct is not None:
        return f"{shares} zu {price} · P&L {row.realized_pnl_pct:+.1f}%"
    return f"{shares} zu {price}"


def _has_note(row: Any) -> bool:
    return any((
        bool(row.basis_text and row.basis_text != "Automatisch aus Trade-Republic-Ausführung übernommen."),
        bool(row.alternative_entry_text),
        bool(row.primary_reasons),
        bool(row.sell_reason),
        bool(row.questionnaire_json),
        any((row.chart_images_json or {}).values()),
    ))


def _context_status(row: Any, contexts: dict[str, Any] | None = None) -> tuple[str, str]:
    stock = row.stock_snapshot_json or {}
    market = row.market_snapshot_json or {}
    sell = getattr(row, "sell_assessment_json", {}) or {}
    explicit = str(stock.get("context_status") or market.get("context_status") or "").lower()
    labels = {
        "archived": "Archiviert",
        "reconstructed": "Rekonstruiert",
        "partial": "Teilweise",
        "missing": "Fehlt",
        "pending": "Wird ergänzt",
        "failed": "Ergänzung fehlgeschlagen",
    }
    if contexts:
        statuses = [context.status for context in contexts.values()]
        rank = {"failed": 0, "missing": 1, "pending": 2, "partial": 3, "reconstructed": 4, "archived": 5}
        status = min(statuses, key=lambda item: rank.get(item, 1))
        return status, labels.get(status, "Fehlt")
    if explicit in labels:
        return explicit, labels[explicit]
    if sell.get("status") == "pending":
        return "pending", labels["pending"]
    if sell.get("status") == "failed":
        return "failed", labels["failed"]
    populated = bool(stock) + bool(market)
    if populated == 2:
        # Legacy snapshots lack a provable information cutoff and must not claim archival truth.
        if all((stock.get("information_cutoff"), stock.get("generated_at"), stock.get("assessment_version"))):
            return "archived", labels["archived"]
        return "partial", labels["partial"]
    if populated or sell.get("status") == "available":
        return "partial", labels["partial"]
    return "missing", labels["missing"]


def _trade_summary(trade_id: str, rows: list[Any]) -> TradeJournalTradeSummary:
    ordered = sorted(rows, key=lambda row: (row.trade_date, row.created_at))
    buys = [row for row in ordered if row.entry_type == "buy"]
    sells = [row for row in ordered if row.entry_type == "sell"]
    bought = sum(float(row.shares or 0) for row in buys)
    sold = sum(float(row.shares or 0) for row in sells)
    remaining = max(0.0, bought - sold)
    statuses = [_context_status(row)[0] for row in ordered]
    rank = {"failed": 0, "missing": 1, "pending": 2, "partial": 3, "reconstructed": 4, "archived": 5}
    context_status = min(statuses, key=lambda item: rank[item]) if statuses else "missing"
    realized_values = [float(row.realized_pnl) for row in sells if row.realized_pnl is not None]
    incomplete = any(row.realized_pnl is None for row in sells)
    realized = None if incomplete and sells else sum(realized_values)
    cost = 0.0
    for row in sells:
        for allocation in (row.portfolio_snapshot_json or {}).get("allocations", []):
            basis = _finite(allocation.get("cost_basis"))
            if basis is not None:
                cost += basis
    invested = sum(float(row.price or 0) * float(row.shares or 0) for row in buys) or None
    if remaining > 1e-9:
        trade_status = "open" if not sells else "partial"
    else:
        trade_status = "closed"
    return TradeJournalTradeSummary(
        id=trade_id,
        ticker=ordered[0].ticker,
        status=trade_status,
        first_entry_date=ordered[0].trade_date.isoformat(),
        last_exit_date=sells[-1].trade_date.isoformat() if sells else None,
        currency=getattr(ordered[0], "currency", "USD") or "USD",
        execution_count=len(ordered),
        buy_count=len(buys),
        sell_count=len(sells),
        bought_shares=round(bought, 8),
        sold_shares=round(sold, 8),
        remaining_shares=round(remaining, 8),
        invested_capital=round(invested, 2) if invested is not None else None,
        realized_pnl=round(realized, 2) if realized is not None else None,
        realized_pnl_pct=round(realized / cost * 100, 2) if realized is not None and cost else None,
        context_status=context_status,
        has_review=any(row.entry_type == "ex_post" or bool(row.questionnaire_json) for row in ordered),
        executions=[_summary_from_row(row) for row in ordered],
    )


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
