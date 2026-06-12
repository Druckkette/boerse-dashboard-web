from __future__ import annotations

import csv
import math
from datetime import UTC, date, datetime, timedelta
from io import StringIO

import pandas as pd

from app.repositories import portfolio as portfolio_repository
from app.repositories import prices as prices_repository
from app.domain.portfolio.trade_republic import (
    estimate_cash_balance,
    parse_transaction_export_csv,
    reconstruct_open_positions,
    resolve_isin_mappings,
)
from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.repositories.prices import PriceRepositoryUnavailable
from app.schemas import (
    KpiCard,
    PortfolioCashFlow,
    PortfolioCashFlowRequest,
    PortfolioCashFlowResponse,
    PortfolioCashFlowsResponse,
    PortfolioCurvePoint,
    PortfolioCurveResponse,
    PortfolioImportRequest,
    PortfolioImportResponse,
    PortfolioImportHistoryItem,
    PortfolioImportHistoryResponse,
    PortfolioImportRow,
    PortfolioPosition,
    PortfolioPositionDeleteResponse,
    PortfolioPositionSizeRequest,
    PortfolioPositionSizeResponse,
    PortfolioPositionWriteRequest,
    PortfolioPositionWriteResponse,
    PortfolioSnapshotResponse,
    PortfolioSellRequest,
    PortfolioSellResponse,
    PortfolioTransaction,
    PortfolioTransactionsResponse,
    TradeRepublicIsinMappingItem,
    TradeRepublicSkippedPosition,
    TradeRepublicTransactionImportRequest,
    TradeRepublicTransactionImportResponse,
)
from app.services.dummy_data import get_portfolio_positions as get_dummy_portfolio_positions
from app.services.dummy_data import get_portfolio_snapshot as get_dummy_portfolio_snapshot


REQUIRED_IMPORT_FIELDS = {"ticker", "shares", "entry_price"}
TR_EXTERNAL_FLOW_TYPES = {
    "customer_inbound",
    "customer_outbound_request",
    "customer_inpayment",
    "transfer_inbound",
    "transfer_instant_inbound",
    "gift",
    "tax_optimization",
}

HEADER_ALIASES = {
    "ticker": {"ticker", "symbol", "wertpapier", "isin_ticker"},
    "name": {"name", "bezeichnung", "instrument", "security", "wertpapiername"},
    "shares": {"shares", "quantity", "qty", "stueck", "stück", "anzahl", "menge"},
    "entry_price": {"entry_price", "buy_price", "avg_price", "average_price", "kaufkurs", "einstand", "einstandskurs"},
    "current_price": {"current_price", "last_price", "kurs", "aktueller_kurs", "market_price"},
    "currency": {"currency", "waehrung", "währung"},
    "buy_date": {"buy_date", "date", "kaufdatum", "opened_at"},
    "broker": {"broker", "bank", "depotbank"},
    "account": {"account", "depot", "portfolio"},
    "note": {"note", "notiz", "comment", "kommentar"},
}


def get_portfolio_positions() -> list[PortfolioPosition]:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        rows = []
    if not rows:
        return get_dummy_portfolio_positions()

    invested = sum(row.current_price * row.shares for row in rows)
    positions: list[PortfolioPosition] = []
    for row in rows:
        market_value = row.current_price * row.shares
        pnl_pct = (row.current_price / row.entry_price - 1) * 100 if row.entry_price else 0
        pnl_abs = (row.current_price - row.entry_price) * row.shares if row.entry_price else 0
        atr_pct = _atr_pct_for_ticker(row.ticker)
        positions.append(
            PortfolioPosition(
                ticker=row.ticker,
                name=row.name,
                shares=row.shares,
                entry_price=row.entry_price,
                current_price=row.current_price,
                market_value=market_value,
                pnl_pct=pnl_pct,
                weight_pct=market_value / invested * 100 if invested else 0,
                atr_pct=atr_pct,
                beta=1,
                status=_status_for_position(pnl_pct, atr_pct),
                pnl_abs=pnl_abs,
                currency=row.currency,
                buy_date=row.buy_date.isoformat() if row.buy_date else None,
                pivot_tag=row.pivot_tag.isoformat() if row.pivot_tag else None,
                stop_pct=row.stop_pct,
                stop_price=row.stop_price,
                broker=row.broker,
                account=row.account,
                note=row.note,
            )
        )
    return positions


def get_portfolio_snapshot() -> PortfolioSnapshotResponse:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        rows = []
    if not rows:
        return get_dummy_portfolio_snapshot()

    positions = get_portfolio_positions()
    invested = sum(position.market_value for position in positions)
    try:
        cash = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable:
        cash = 0.0
    total = invested + cash
    portfolio_atr_pct = sum(position.weight_pct * position.atr_pct for position in positions) / 100 if positions else 0
    total_pnl_abs = sum(position.pnl_abs for position in positions)
    cost_basis = sum(position.entry_price * position.shares for position in positions)
    total_pnl_pct = total_pnl_abs / cost_basis * 100 if cost_basis else 0.0
    return PortfolioSnapshotResponse(
        as_of=datetime.now(UTC).isoformat(),
        total_value=total,
        invested_value=invested,
        cash_balance=cash,
        cash_ratio_pct=cash / total * 100 if total else 0,
        portfolio_atr_pct=portfolio_atr_pct,
        beta_balancer=1,
        max_depot_loss_pct=sum(position.weight_pct * 0.08 for position in positions) / 100,
        kpis=[
            KpiCard(label="Depotwert", value=f"{total:,.0f} EUR", detail="aus Import", tone="neutral"),
            KpiCard(label="Positionen", value=str(len(positions)), detail="offen", tone="good"),
            KpiCard(
                label="Unrealisiert",
                value=f"{total_pnl_abs:+,.0f} EUR",
                detail=f"{total_pnl_pct:+.1f}% ggü. Einstand",
                tone="good" if total_pnl_abs >= 0 else "bad",
            ),
            KpiCard(label="Cashquote", value=f"{cash / total * 100:.1f}%" if total else "0.0%", detail=f"{cash:,.0f} EUR", tone="neutral"),
            KpiCard(
                label="Portfolio ATR",
                value=f"{portfolio_atr_pct:.2f}%",
                detail="gewichtet aus Price Cache" if portfolio_atr_pct else "Price Cache fehlt",
                tone=_tone_for_portfolio_atr(portfolio_atr_pct),
            ),
        ],
        positions=positions,
    )


def get_portfolio_curve(days: int = 370) -> PortfolioCurveResponse:
    tr_curve = _get_trade_republic_curve(days=days)
    if tr_curve is not None:
        return tr_curve

    try:
        rows = portfolio_repository.list_open_positions()
        cash = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable:
        rows = []
        cash = 0.0
    if not rows:
        return PortfolioCurveResponse(
            as_of=datetime.now(UTC).date().isoformat(),
            source="missing",
            data_status="missing",
            message="Keine offenen Positionen für die Depotkurve.",
            points=[],
        )

    start_date = date.today() - timedelta(days=max(30, min(2500, days)))
    series_map: dict[str, pd.Series] = {}
    for row in rows:
        try:
            price_rows = prices_repository.list_price_bars(row.ticker, start_date=start_date)
        except PriceRepositoryUnavailable:
            price_rows = []
        points = [
            (pd.Timestamp(price.date), float(price.close))
            for price in price_rows
            if price.close is not None
        ]
        if points:
            series = pd.Series(
                [item[1] for item in points],
                index=pd.DatetimeIndex([item[0] for item in points]),
                dtype=float,
            ).sort_index()
            series_map[row.ticker] = series[~series.index.duplicated(keep="last")]

    if not series_map:
        return PortfolioCurveResponse(
            as_of=datetime.now(UTC).date().isoformat(),
            source="missing",
            data_status="missing",
            message="Für die offenen Positionen fehlen Price-Bars im Cache.",
            points=[],
        )

    all_dates = sorted(set().union(*(series.index for series in series_map.values())))
    frame = pd.DataFrame(index=pd.DatetimeIndex(all_dates))
    for row in rows:
        series = series_map.get(row.ticker)
        if series is None:
            continue
        frame[row.ticker] = series.reindex(frame.index).ffill()

    points: list[PortfolioCurvePoint] = []
    index_values: list[float] = []
    for timestamp, values in frame.iterrows():
        positions_value = 0.0
        for row in rows:
            close = values.get(row.ticker)
            if pd.notna(close):
                positions_value += float(close) * row.shares
        depot_value = positions_value + cash
        if depot_value <= 0:
            continue
        if not index_values:
            base = depot_value
        portfolio_index = depot_value / base * 100
        index_values.append(portfolio_index)
        sma10 = float(pd.Series(index_values).rolling(10, min_periods=10).mean().iloc[-1]) if len(index_values) >= 10 else None
        sma21 = float(pd.Series(index_values).rolling(21, min_periods=21).mean().iloc[-1]) if len(index_values) >= 21 else None
        points.append(
            PortfolioCurvePoint(
                date=timestamp.date().isoformat(),
                depot_value=round(depot_value, 2),
                positions_value=round(positions_value, 2),
                cash=round(cash, 2),
                portfolio_index=round(portfolio_index, 2),
                portfolio_index_sma10=round(sma10, 2) if sma10 is not None else None,
                portfolio_index_sma21=round(sma21, 2) if sma21 is not None else None,
            )
        )

    return PortfolioCurveResponse(
        as_of=points[-1].date if points else datetime.now(UTC).date().isoformat(),
        source="database",
        data_status="fresh",
        message="Depotkurve aus offenen Positionen, Price Cache und Cash-Bestand.",
        points=points,
    )


def _get_trade_republic_curve(days: int) -> PortfolioCurveResponse | None:
    try:
        transactions = portfolio_repository.list_trade_republic_transactions()
    except PortfolioRepositoryUnavailable:
        return None
    if not transactions:
        return None

    start_date = min(row.date for row in transactions)
    end_date = date.today()
    if start_date > end_date:
        return None
    calendar = pd.DatetimeIndex(pd.date_range(start_date, end_date, freq="B"))
    if calendar.empty:
        return None

    tickers = sorted({row.ticker for row in transactions if row.ticker})
    positions_value = pd.Series(0.0, index=calendar)
    missing_price_tickers: list[str] = []
    trade_price_fallbacks: list[str] = []

    for ticker in tickers:
        ticker_transactions = [row for row in transactions if row.ticker == ticker]
        shares = pd.Series(0.0, index=calendar)
        running = 0.0
        for row in ticker_transactions:
            delta = _signed_share_delta(row.transaction_type, row.shares)
            if row.transaction_type == "split":
                running = max(row.shares, 0.0)
            else:
                running = max(running + delta, 0.0)
            shares.loc[shares.index >= pd.Timestamp(row.date)] = running

        cached_prices = _cached_price_series(ticker, start_date)
        if cached_prices.empty:
            cached_prices = _trade_price_fallback_series(ticker_transactions, calendar)
            if cached_prices.empty:
                missing_price_tickers.append(ticker)
                continue
            trade_price_fallbacks.append(ticker)
        aligned_prices = cached_prices.reindex(calendar, method="ffill").ffill().bfill().fillna(0.0)
        positions_value = positions_value.add(shares.values * aligned_prices.values, fill_value=0.0)

    cash_daily = pd.Series(0.0, index=calendar)
    external_daily = pd.Series(0.0, index=calendar)
    for row in transactions:
        day = pd.Timestamp(row.date)
        if day not in cash_daily.index:
            next_days = cash_daily.index[cash_daily.index >= day]
            if next_days.empty:
                continue
            day = next_days[0]
        cash_daily.loc[day] += row.net_amount
        if row.transaction_type in TR_EXTERNAL_FLOW_TYPES:
            external_daily.loc[day] += row.net_amount

    curve = pd.DataFrame(
        {
            "date": calendar,
            "positions_value": positions_value.values,
            "cash": cash_daily.cumsum().values,
            "external_flow": external_daily.values,
        }
    )
    curve["depot_value"] = curve["positions_value"] + curve["cash"]
    first_active = curve["depot_value"].abs().gt(1e-9)
    if not first_active.any():
        return None
    curve = curve.loc[first_active.idxmax() :].reset_index(drop=True)

    window_start = pd.Timestamp(date.today() - timedelta(days=max(30, min(2500, days))))
    curve = curve[curve["date"] >= window_start].reset_index(drop=True)
    if curve.empty:
        return None

    index_values = [100.0]
    depot_values = curve["depot_value"].tolist()
    external_values = curve["external_flow"].tolist()
    for idx in range(1, len(curve)):
        previous = float(depot_values[idx - 1])
        current = float(depot_values[idx])
        external = float(external_values[idx])
        daily_return = (current - previous - external) / previous if previous > 0 else 0.0
        index_values.append(index_values[-1] * (1.0 + daily_return))
    curve["portfolio_index"] = index_values
    curve["portfolio_index_sma10"] = curve["portfolio_index"].rolling(10, min_periods=10).mean()
    curve["portfolio_index_sma21"] = curve["portfolio_index"].rolling(21, min_periods=21).mean()

    points = [
        PortfolioCurvePoint(
            date=pd.Timestamp(row.date).date().isoformat(),
            depot_value=round(float(row.depot_value), 2),
            positions_value=round(float(row.positions_value), 2),
            cash=round(float(row.cash), 2),
            portfolio_index=round(float(row.portfolio_index), 2),
            portfolio_index_sma10=round(float(row.portfolio_index_sma10), 2)
            if pd.notna(row.portfolio_index_sma10)
            else None,
            portfolio_index_sma21=round(float(row.portfolio_index_sma21), 2)
            if pd.notna(row.portfolio_index_sma21)
            else None,
        )
        for row in curve.itertuples()
    ]
    details = []
    if trade_price_fallbacks:
        details.append("Trade-Price-Fallback: " + ", ".join(trade_price_fallbacks))
    if missing_price_tickers:
        details.append("Kursdaten fehlen: " + ", ".join(missing_price_tickers))
    message = "Depotkurve aus gespeichertem Trade-Republic-Transaktionsexport."
    if details:
        message += " " + " · ".join(details)

    return PortfolioCurveResponse(
        as_of=points[-1].date if points else datetime.now(UTC).date().isoformat(),
        source="trade_republic_transactions",
        data_status="fresh" if points else "missing",
        message=message,
        points=points,
    )


def _cached_price_series(ticker: str, start_date: date) -> pd.Series:
    try:
        rows = prices_repository.list_price_bars(ticker, start_date=start_date)
    except PriceRepositoryUnavailable:
        rows = []
    values = [(pd.Timestamp(row.date), float(row.close)) for row in rows if row.close is not None]
    if not values:
        return pd.Series(dtype=float)
    return pd.Series(
        [item[1] for item in values],
        index=pd.DatetimeIndex([item[0] for item in values]),
        dtype=float,
    ).sort_index()


def _trade_price_fallback_series(transactions: list[portfolio_repository.TradeRepublicStoredTransactionRow], calendar: pd.DatetimeIndex) -> pd.Series:
    values = [
        (pd.Timestamp(row.date), float(row.price))
        for row in transactions
        if row.price is not None and row.price > 0 and row.transaction_type in {"buy", "sell", "transfer_in", "sell_cancelled"}
    ]
    if not values:
        return pd.Series(dtype=float)
    series = pd.Series(
        [item[1] for item in values],
        index=pd.DatetimeIndex([item[0] for item in values]),
        dtype=float,
    ).sort_index()
    return series.reindex(calendar, method="ffill").ffill().bfill()


def _signed_share_delta(transaction_type: str, shares: float) -> float:
    amount = abs(float(shares or 0.0))
    if transaction_type in {"sell", "transfer_out", "warrant_exercise", "insolvency_proceedings", "delisted", "expiration"}:
        return -amount
    if transaction_type in {"buy", "transfer_in", "sell_cancelled"}:
        return amount
    return 0.0


def calculate_position_size(payload: PortfolioPositionSizeRequest) -> PortfolioPositionSizeResponse:
    risk_budget = payload.depot_value * (payload.risk_per_position_pct / 100)
    risk_per_share = payload.buy_price * (payload.stop_pct / 100)
    stop_price = payload.buy_price * (1 - payload.stop_pct / 100)
    max_shares_by_loss = math.floor(risk_budget / risk_per_share) if risk_budget > 0 and risk_per_share > 0 else 0
    max_position_value_by_loss = max_shares_by_loss * payload.buy_price

    warnings: list[str] = []
    balancer_score: float | None = None
    max_weight_pct_by_balancer: float | None = None
    max_position_value_by_balancer: float | None = None
    max_shares_by_balancer: int | None = None
    current_price = payload.current_price or payload.buy_price

    if payload.beta is not None and payload.atr_pct is not None and payload.market_atr_pct:
        balancer_score = 0.60 * payload.beta + 0.40 * (payload.atr_pct / payload.market_atr_pct)
        if balancer_score > 0:
            max_weight = payload.target_risk_contribution / balancer_score
            max_weight_pct_by_balancer = max_weight * 100
            max_position_value_by_balancer = payload.depot_value * max_weight
            max_shares_by_balancer = (
                math.floor(max_position_value_by_balancer / current_price)
                if current_price > 0 and max_position_value_by_balancer > 0
                else 0
            )
    else:
        warnings.append("Beta-Balancer nicht berechnet: ATR%, Beta oder Markt-ATR fehlen.")

    if max_shares_by_balancer is None:
        recommended = max_shares_by_loss
        limiting_factor = "insufficient_data"
    elif max_shares_by_loss <= max_shares_by_balancer:
        recommended = max_shares_by_loss
        limiting_factor = "loss_budget"
    else:
        recommended = max_shares_by_balancer
        limiting_factor = "beta_balancer"

    return PortfolioPositionSizeResponse(
        risk_budget=round(risk_budget, 2),
        risk_per_share=round(risk_per_share, 4),
        stop_price=round(stop_price, 4),
        max_shares_by_loss_budget=max_shares_by_loss,
        max_position_value_by_loss_budget=round(max_position_value_by_loss, 2),
        balancer_score=round(balancer_score, 4) if balancer_score is not None else None,
        max_weight_pct_by_balancer=round(max_weight_pct_by_balancer, 4)
        if max_weight_pct_by_balancer is not None
        else None,
        max_position_value_by_balancer=round(max_position_value_by_balancer, 2)
        if max_position_value_by_balancer is not None
        else None,
        max_shares_by_balancer=max_shares_by_balancer,
        recommended_max_shares=recommended,
        recommended_position_value=round(recommended * current_price, 2),
        limiting_factor=limiting_factor,
        warnings=warnings,
    )


def upsert_portfolio_position(payload: PortfolioPositionWriteRequest) -> PortfolioPositionWriteResponse:
    write = portfolio_repository.PortfolioPositionWrite(
        ticker=payload.ticker,
        name=payload.name,
        shares=payload.shares,
        entry_price=payload.entry_price,
        current_price=payload.current_price,
        currency=payload.currency.upper(),
        buy_date=_parse_date(payload.buy_date),
        pivot_tag=_parse_date(payload.pivot_tag),
        stop_pct=payload.stop_pct,
        broker=payload.broker,
        account=payload.account,
        note=payload.note,
        record_transaction=payload.record_transaction,
    )
    row = portfolio_repository.upsert_position(write)
    return PortfolioPositionWriteResponse(position=_position_from_row(row, invested=row.current_price * row.shares))


def delete_portfolio_position(ticker: str) -> PortfolioPositionDeleteResponse:
    clean = ticker.strip().upper()
    return PortfolioPositionDeleteResponse(ticker=clean, closed=portfolio_repository.close_position(clean))


def sell_portfolio_position(ticker: str, payload: PortfolioSellRequest) -> PortfolioSellResponse:
    clean = ticker.strip().upper()
    row, transaction = portfolio_repository.sell_position(
        portfolio_repository.PortfolioSellWrite(
            ticker=clean,
            shares=payload.shares,
            price=payload.price,
            date=_parse_date(payload.date) or date.today(),
            currency=payload.currency.upper(),
            fees=payload.fees,
            tax=payload.tax,
            note=payload.note,
        )
    )
    cash_balance = portfolio_repository.get_cash_balance()
    return PortfolioSellResponse(
        ticker=clean,
        remaining_position=_position_from_row(row, invested=row.current_price * row.shares) if row else None,
        transaction=_transaction_schema(transaction),
        cash_balance=cash_balance,
    )


def get_portfolio_transactions(limit: int = 250) -> PortfolioTransactionsResponse:
    try:
        rows = portfolio_repository.list_transactions(limit=limit)
    except PortfolioRepositoryUnavailable:
        rows = []
    return PortfolioTransactionsResponse(transactions=[_transaction_schema(row) for row in rows])


def get_portfolio_cash_flows(limit: int = 250) -> PortfolioCashFlowsResponse:
    try:
        rows = portfolio_repository.list_cash_flows(limit=limit)
        cash_balance = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable:
        rows = []
        cash_balance = 0.0
    return PortfolioCashFlowsResponse(
        cash_flows=[_cash_flow_schema(row) for row in rows],
        cash_balance=cash_balance,
    )


def create_portfolio_cash_flow(payload: PortfolioCashFlowRequest) -> PortfolioCashFlowResponse:
    row = portfolio_repository.add_cash_flow(
        portfolio_repository.PortfolioCashFlowWrite(
            date=_parse_date(payload.date) or date.today(),
            amount=payload.amount,
            flow_type=payload.flow_type,
            currency=payload.currency.upper(),
            broker=payload.broker,
            note=payload.note,
        )
    )
    return PortfolioCashFlowResponse(
        cash_flow=_cash_flow_schema(row),
        cash_balance=portfolio_repository.get_cash_balance(),
    )


def get_portfolio_import_history(limit: int = 100) -> PortfolioImportHistoryResponse:
    try:
        rows = portfolio_repository.list_import_history(limit=limit)
    except PortfolioRepositoryUnavailable:
        rows = []
    return PortfolioImportHistoryResponse(
        imports=[
            PortfolioImportHistoryItem(
                id=row.id,
                source=row.source,
                file_name=row.file_name,
                status=row.status,
                rows_total=row.rows_total,
                rows_imported=row.rows_imported,
                error_message=row.error_message,
                created_at=row.created_at,
                finished_at=row.finished_at,
            )
            for row in rows
        ]
    )


def import_portfolio_positions(payload: PortfolioImportRequest) -> PortfolioImportResponse:
    parse_result = parse_positions_csv(payload.content)
    if parse_result.errors or payload.dry_run:
        return PortfolioImportResponse(
            ok=not parse_result.errors,
            dry_run=payload.dry_run,
            rows_total=parse_result.rows_total,
            rows_imported=0,
            positions=parse_result.positions,
            errors=parse_result.errors,
            warnings=parse_result.warnings,
        )

    result = portfolio_repository.upsert_imported_positions(
        parse_result.positions,
        source=payload.source,
        file_name=payload.file_name,
        replace_open_positions=payload.replace_open_positions,
    )
    return PortfolioImportResponse(
        ok=True,
        dry_run=False,
        import_id=result.import_id,
        rows_total=parse_result.rows_total,
        rows_imported=result.rows_imported,
        positions=parse_result.positions,
        warnings=parse_result.warnings,
    )


def import_trade_republic_transaction_export(
    payload: TradeRepublicTransactionImportRequest,
) -> TradeRepublicTransactionImportResponse:
    try:
        rows = parse_transaction_export_csv(payload.content)
    except ValueError as exc:
        return TradeRepublicTransactionImportResponse(
            ok=False,
            dry_run=payload.dry_run,
            rows_total=0,
            rows_imported=0,
            transactions_total=0,
            cash_balance_estimate=0.0,
            positions=[],
            mappings=[],
            errors=[str(exc)],
        )

    try:
        saved_mappings = portfolio_repository.list_isin_mappings()
    except PortfolioRepositoryUnavailable:
        saved_mappings = {}
    diagnostics = resolve_isin_mappings(rows, saved_mappings=saved_mappings, overrides=payload.isin_overrides)
    ticker_by_isin = {
        str(item["isin"]).upper(): str(item["ticker"]).upper()
        for item in diagnostics
        if str(item.get("ticker") or "").strip()
    }
    reconstructed, skipped = reconstruct_open_positions(rows, ticker_by_isin)
    positions = [
        PortfolioImportRow(
            ticker=item.ticker,
            name=item.name,
            shares=item.shares,
            entry_price=item.avg_buy_price,
            current_price=None,
            currency=item.currency,
            buy_date=item.first_buy_date,
            broker="Trade Republic",
            account="Trade Republic",
            note=f"TR-Transaktionsimport / ISIN {item.isin}",
            warnings=[],
        )
        for item in reconstructed
    ]
    mappings = [
        TradeRepublicIsinMappingItem(
            isin=str(item["isin"]),
            name=str(item["name"]),
            asset_class=str(item["asset_class"]),
            ticker=str(item["ticker"] or ""),
            source=item["source"],
        )
        for item in diagnostics
    ]
    skipped_positions = [
        TradeRepublicSkippedPosition(
            isin=item.isin,
            name=item.name,
            shares=item.shares,
            asset_class=item.asset_class,
            reason=item.reason,
        )
        for item in skipped
    ]
    warnings = []
    missing_mappings = [item.isin for item in mappings if not item.ticker]
    if missing_mappings:
        warnings.append("Für diese ISINs fehlt ein Yahoo-Ticker: " + ", ".join(missing_mappings))
    if skipped_positions:
        warnings.append(f"{len(skipped_positions)} offene Position(en) werden nicht automatisch importiert.")

    if payload.dry_run:
        return TradeRepublicTransactionImportResponse(
            ok=True,
            dry_run=True,
            rows_total=len(rows),
            rows_imported=0,
            transactions_total=len(rows),
            cash_balance_estimate=estimate_cash_balance(rows),
            positions=positions,
            mappings=mappings,
            skipped_positions=skipped_positions,
            warnings=warnings,
        )

    result = portfolio_repository.import_trade_republic_transactions(
        transactions=rows,
        positions=reconstructed,
        mappings=ticker_by_isin,
        file_name=payload.file_name,
        replace_open_positions=payload.replace_open_positions,
    )
    return TradeRepublicTransactionImportResponse(
        ok=True,
        dry_run=False,
        import_id=result.import_id,
        rows_total=len(rows),
        rows_imported=result.rows_imported,
        transactions_total=result.transactions_imported,
        cash_balance_estimate=estimate_cash_balance(rows),
        positions=positions,
        mappings=mappings,
        skipped_positions=skipped_positions,
        warnings=warnings,
    )


def _position_from_row(row: portfolio_repository.PortfolioPositionRow, *, invested: float) -> PortfolioPosition:
    market_value = row.current_price * row.shares
    pnl_pct = (row.current_price / row.entry_price - 1) * 100 if row.entry_price else 0
    pnl_abs = (row.current_price - row.entry_price) * row.shares if row.entry_price else 0
    atr_pct = _atr_pct_for_ticker(row.ticker)
    return PortfolioPosition(
        ticker=row.ticker,
        name=row.name,
        shares=row.shares,
        entry_price=row.entry_price,
        current_price=row.current_price,
        market_value=market_value,
        pnl_pct=pnl_pct,
        weight_pct=market_value / invested * 100 if invested else 100,
        atr_pct=atr_pct,
        beta=1,
        status=_status_for_position(pnl_pct, atr_pct),
        pnl_abs=pnl_abs,
        currency=row.currency,
        buy_date=row.buy_date.isoformat() if row.buy_date else None,
        pivot_tag=row.pivot_tag.isoformat() if row.pivot_tag else None,
        stop_pct=row.stop_pct,
        stop_price=row.stop_price,
        broker=row.broker,
        account=row.account,
        note=row.note,
    )


def _transaction_schema(row: portfolio_repository.PortfolioTransactionRow) -> PortfolioTransaction:
    return PortfolioTransaction(
        id=row.id,
        ticker=row.ticker,
        date=row.date.isoformat(),
        transaction_type=row.transaction_type,
        shares=row.shares,
        price=row.price,
        fees=row.fees,
        tax=row.tax,
        gross_amount=row.gross_amount,
        net_amount=row.net_amount,
        currency=row.currency,
        broker=row.broker,
        external_id=row.external_id,
    )


def _cash_flow_schema(row: portfolio_repository.PortfolioCashFlowRow) -> PortfolioCashFlow:
    return PortfolioCashFlow(
        id=row.id,
        date=row.date.isoformat(),
        amount=row.amount,
        flow_type=row.flow_type,
        currency=row.currency,
        broker=row.broker,
        note=row.note,
    )


class PortfolioCsvParseResult:
    def __init__(
        self,
        *,
        positions: list[PortfolioImportRow],
        rows_total: int,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.positions = positions
        self.rows_total = rows_total
        self.errors = errors or []
        self.warnings = warnings or []


def parse_positions_csv(content: str) -> PortfolioCsvParseResult:
    clean_content = content.strip("\ufeff \n\r\t")
    if not clean_content:
        return PortfolioCsvParseResult(positions=[], rows_total=0, errors=["CSV-Inhalt ist leer."])

    dialect = _sniff_dialect(clean_content)
    reader = csv.DictReader(StringIO(clean_content), dialect=dialect)
    if not reader.fieldnames:
        return PortfolioCsvParseResult(positions=[], rows_total=0, errors=["CSV-Header fehlt."])

    normalized_headers = {header: _canonical_header(header) for header in reader.fieldnames}
    present = {canonical for canonical in normalized_headers.values() if canonical}
    missing = sorted(REQUIRED_IMPORT_FIELDS - present)
    if missing:
        return PortfolioCsvParseResult(
            positions=[],
            rows_total=0,
            errors=[f"Pflichtspalten fehlen: {', '.join(missing)}."],
            warnings=[f"Erkannte Spalten: {', '.join(reader.fieldnames)}"],
        )

    positions: list[PortfolioImportRow] = []
    errors: list[str] = []
    warnings: list[str] = []
    rows_total = 0
    for line_number, raw_row in enumerate(reader, start=2):
        rows_total += 1
        row = {
            canonical: (raw_row.get(header) or "").strip()
            for header, canonical in normalized_headers.items()
            if canonical
        }
        if not any(row.values()):
            continue

        ticker = row.get("ticker", "").upper().replace(" ", "")
        shares = _parse_number(row.get("shares", ""))
        entry_price = _parse_number(row.get("entry_price", ""))
        if not ticker:
            errors.append(f"Zeile {line_number}: ticker fehlt.")
            continue
        if shares is None or shares <= 0:
            errors.append(f"Zeile {line_number}: shares ist ungültig.")
            continue
        if entry_price is None or entry_price <= 0:
            errors.append(f"Zeile {line_number}: entry_price ist ungültig.")
            continue

        current_price = _parse_number(row.get("current_price", ""))
        row_warnings: list[str] = []
        if current_price is None:
            row_warnings.append("Kein aktueller Kurs in CSV; Price Cache oder Einstandskurs wird genutzt.")
        positions.append(
            PortfolioImportRow(
                ticker=ticker,
                name=row.get("name", "") or ticker,
                shares=shares,
                entry_price=entry_price,
                current_price=current_price,
                currency=(row.get("currency", "") or "EUR").upper(),
                buy_date=row.get("buy_date") or None,
                broker=row.get("broker", ""),
                account=row.get("account", ""),
                note=row.get("note", ""),
                warnings=row_warnings,
            )
        )

    if not positions and not errors:
        errors.append("Keine importierbaren Positionen gefunden.")
    duplicate_tickers = sorted({row.ticker for row in positions if sum(1 for item in positions if item.ticker == row.ticker) > 1})
    if duplicate_tickers:
        warnings.append(f"Doppelte Ticker in CSV: {', '.join(duplicate_tickers)}. Der letzte Import überschreibt später denselben offenen Ticker.")
    return PortfolioCsvParseResult(positions=positions, rows_total=rows_total, errors=errors, warnings=warnings)


def _status_for_position(pnl_pct: float, atr_pct: float) -> str:
    if pnl_pct <= -8:
        return "sell"
    if pnl_pct <= -4:
        return "risk"
    if atr_pct >= 6:
        return "watch"
    if pnl_pct >= 25:
        return "watch"
    return "ok"


def _atr_pct_for_ticker(ticker: str) -> float:
    try:
        rows = prices_repository.list_price_bars(ticker)
    except PriceRepositoryUnavailable:
        rows = []
    if len(rows) < 15:
        return 0.0

    frame_rows = []
    for row in rows:
        if row.close is None:
            continue
        close = float(row.close)
        open_price = float(row.open) if row.open is not None else close
        high = float(row.high) if row.high is not None else max(open_price, close)
        low = float(row.low) if row.low is not None else min(open_price, close)
        frame_rows.append({"date": row.date, "high": high, "low": low, "close": close})
    if len(frame_rows) < 15:
        return 0.0

    frame = pd.DataFrame(frame_rows).drop_duplicates(subset=["date"], keep="last").sort_values("date")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr14 = true_range.rolling(14, min_periods=14).mean().dropna()
    last_close = close.dropna().iloc[-1] if not close.dropna().empty else None
    if atr14.empty or not last_close or last_close <= 0:
        return 0.0
    return float(round(float(atr14.iloc[-1]) / float(last_close) * 100, 2))


def _tone_for_portfolio_atr(value: float) -> str:
    if value <= 0:
        return "neutral"
    if value <= 2.5:
        return "good"
    if value <= 4:
        return "neutral"
    if value <= 6:
        return "warning"
    return "bad"


def _sniff_dialect(content: str) -> csv.Dialect:
    sample = content[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def _canonical_header(header: str) -> str | None:
    clean = header.strip().lower().replace(" ", "_").replace("-", "_")
    for canonical, aliases in HEADER_ALIASES.items():
        if clean in aliases:
            return canonical
    return None


def _parse_number(value: str) -> float | None:
    clean = value.strip()
    if not clean:
        return None
    clean = clean.replace("\u00a0", "").replace(" ", "")
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    else:
        clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            return parsed.date()
    except Exception:
        return None
    return None
