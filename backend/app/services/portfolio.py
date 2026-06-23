from __future__ import annotations

import csv
import math
from datetime import UTC, date, datetime, timedelta
from io import StringIO

import pandas as pd

from app.repositories import portfolio as portfolio_repository
from app.repositories import prices as prices_repository
from app.repositories import fundamentals as fundamentals_repository
from app.repositories import relative_strength as relative_strength_repository
from app.domain.portfolio.trade_republic import (
    TradeRepublicPosition as DomainTradeRepublicPosition,
    NON_SHARE_TYPES,
    POSITION_ASSET_CLASSES,
    SHARE_DECREASE_TYPES,
    SHARE_INCREASE_TYPES,
    estimate_cash_balance,
    normalize_transaction_type,
    parse_transaction_export_csv,
    reconstruct_open_positions,
    resolve_isin_mappings,
)
from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.repositories.prices import PriceRepositoryUnavailable
from app.repositories.fundamentals import FundamentalsRepositoryUnavailable
from app.repositories.relative_strength import RelativeStrengthRepositoryUnavailable
from app.services.fx import FxRate, eur_to_usd, get_eur_usd_rate
from app.schemas import (
    BuyStrengthAssessmentResponse,
    BuyStrengthCheck,
    BuyStrengthOverviewResponse,
    BuyStrengthSummaryItem,
    IsinMappingListResponse,
    IsinMappingPatchRequest,
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
    PortfolioPositionStopRequest,
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


REQUIRED_IMPORT_FIELDS = {"ticker", "shares", "entry_price"}
TR_EXTERNAL_FLOW_TYPES = {
    "cash_deposit",
    "cash_withdrawal",
    "customer_deposit",
    "customer_inbound",
    "customer_outbound_request",
    "customer_outbound",
    "customer_inpayment",
    "customer_outpayment",
    "customer_withdrawal",
    "deposit",
    "inbound_payment",
    "outbound_payment",
    "pay_in",
    "pay_out",
    "transfer_inbound",
    "transfer_instant_inbound",
    "transfer_outbound",
    "withdrawal",
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
DEFAULT_BUY_STRENGTH_WEEKS = 3
DEFAULT_PORTFOLIO_CURVE_DAYS = 370


def get_portfolio_positions() -> list[PortfolioPosition]:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        rows = []
    if not rows:
        return []

    rows = [_normalize_trade_republic_row_to_usd(row) for row in rows]
    invested = sum(row.current_price * row.shares for row in rows)
    market_atr_pct = _market_atr_pct()
    positions: list[PortfolioPosition] = []
    for row in rows:
        market_value = row.current_price * row.shares
        pnl_pct = (row.current_price / row.entry_price - 1) * 100 if row.entry_price else 0
        pnl_abs = (row.current_price - row.entry_price) * row.shares if row.entry_price else 0
        atr_pct = _atr_pct_for_ticker(row.ticker)
        beta = _beta_for_ticker(row.ticker)
        weight_pct = market_value / invested * 100 if invested else 0
        beta_balancer_score = _beta_balancer_score(beta=beta, atr_pct=atr_pct, market_atr_pct=market_atr_pct)
        risk_contribution = _risk_contribution(weight_pct=weight_pct, beta_balancer_score=beta_balancer_score)
        position_loss_risk = _position_loss_risk(row)
        positions.append(
            PortfolioPosition(
                ticker=row.ticker,
                name=row.name,
                shares=row.shares,
                entry_price=row.entry_price,
                current_price=row.current_price,
                market_value=market_value,
                pnl_pct=pnl_pct,
                weight_pct=weight_pct,
                atr_pct=atr_pct,
                beta=beta,
                beta_balancer_score=beta_balancer_score,
                risk_contribution=risk_contribution,
                position_loss_risk=position_loss_risk,
                position_loss_risk_pct=position_loss_risk / invested * 100 if invested and position_loss_risk is not None else None,
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
        return _empty_portfolio_snapshot()

    positions = get_portfolio_positions()
    invested = sum(position.market_value for position in positions)
    try:
        cash = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable:
        cash = 0.0
    display_currency = _portfolio_display_currency(positions)
    if display_currency == "USD":
        fx_rate = get_eur_usd_rate()
        cash = round(float(eur_to_usd(cash, rate=fx_rate) or 0.0), 2)
    total = invested + cash
    portfolio_atr_pct = sum(position.weight_pct * position.atr_pct for position in positions) / 100 if positions else 0
    portfolio_beta_balancer = sum(
        position.risk_contribution or 0.0
        for position in positions
    )
    position_loss_values = [position.position_loss_risk for position in positions]
    max_depot_loss_available = bool(positions) and all(value is not None for value in position_loss_values)
    max_depot_loss_abs = sum(float(value or 0.0) for value in position_loss_values) if max_depot_loss_available else None
    max_depot_loss_pct = max_depot_loss_abs / total * 100 if total and max_depot_loss_abs is not None else 0.0
    market_atr_pct = _market_atr_pct()
    total_pnl_abs = sum(position.pnl_abs for position in positions)
    cost_basis = sum(position.entry_price * position.shares for position in positions)
    total_pnl_pct = total_pnl_abs / cost_basis * 100 if cost_basis else 0.0
    kpis = [
        KpiCard(label="Depotwert", value=f"{total:,.0f} {display_currency}", detail="aus Import", tone="neutral"),
        KpiCard(label="Positionen", value=str(len(positions)), detail="offen", tone="good"),
        KpiCard(
            label="Unrealisiert",
            value=f"{total_pnl_abs:+,.0f} {display_currency}",
            detail=f"{total_pnl_pct:+.1f}% ggü. Einstand",
            tone="good" if total_pnl_abs >= 0 else "bad",
        ),
        KpiCard(label="Cashquote", value=f"{cash / total * 100:.1f}%" if total else "0.0%", detail=f"{cash:,.0f} {display_currency}", tone="neutral"),
        KpiCard(
            label="Portfolio ATR",
            value=f"{portfolio_atr_pct:.2f}%",
            detail=_portfolio_atr_detail(portfolio_atr_pct),
            tone=_tone_for_portfolio_atr(portfolio_atr_pct),
        ),
        KpiCard(
            label="Portfolio Beta Balancer",
            value=f"{portfolio_beta_balancer:.2f}",
            detail="Summe Positionsanteil x Beta-Balancer-Score",
            tone=_tone_for_portfolio_beta_balancer(portfolio_beta_balancer),
        ),
    ]
    if max_depot_loss_available and max_depot_loss_abs is not None:
        kpis.append(
            KpiCard(
                label="Maximaler Depotverlust",
                value=f"{max_depot_loss_abs:,.0f} {display_currency}",
                detail=f"{max_depot_loss_pct:.1f}% des Depots inkl. Cash",
                tone=_tone_for_max_depot_loss(max_depot_loss_pct),
            )
        )
    return PortfolioSnapshotResponse(
        as_of=datetime.now(UTC).isoformat(),
        total_value=total,
        invested_value=invested,
        cash_balance=cash,
        cash_ratio_pct=cash / total * 100 if total else 0,
        portfolio_atr_pct=portfolio_atr_pct,
        market_atr_pct=market_atr_pct,
        beta_balancer=portfolio_beta_balancer,
        max_depot_loss_abs=max_depot_loss_abs,
        max_depot_loss_available=max_depot_loss_available,
        max_depot_loss_pct=max_depot_loss_pct,
        kpis=kpis,
        positions=positions,
    )


def get_buy_strength_overview(weeks: int = DEFAULT_BUY_STRENGTH_WEEKS) -> BuyStrengthOverviewResponse:
    window_days = _buy_strength_window_days(weeks)
    items: list[BuyStrengthSummaryItem] = []
    for position in get_portfolio_positions():
        buy_date = _parse_date(position.buy_date)
        if buy_date is None:
            continue
        age_days = (date.today() - buy_date).days
        if age_days < 0 or age_days > window_days:
            continue
        assessment = get_buy_strength_assessment(position.ticker, weeks=weeks)
        items.append(
            BuyStrengthSummaryItem(
                ticker=assessment.ticker,
                name=assessment.name,
                buy_date=assessment.buy_date or buy_date.isoformat(),
                age_days=assessment.age_days if assessment.age_days is not None else age_days,
                pnl_pct=assessment.pnl_pct,
                current_price=assessment.current_price,
                entry_price=assessment.entry_price,
                checks_passed=sum(1 for check in assessment.checks if check.passed),
                checks_total=len(assessment.checks),
                warnings_active=sum(1 for check in assessment.warnings if not check.passed),
                warnings_total=len(assessment.warnings),
                status=assessment.status,
                status_label=assessment.status_label,
                message=assessment.message,
            )
        )

    items.sort(key=lambda item: (item.status in {"risk", "watch"}, item.age_days), reverse=True)
    return BuyStrengthOverviewResponse(
        as_of=datetime.now(UTC).isoformat(),
        window_days=window_days,
        items=items,
    )


def get_buy_strength_assessment(ticker: str, weeks: int = DEFAULT_BUY_STRENGTH_WEEKS) -> BuyStrengthAssessmentResponse:
    window_days = _buy_strength_window_days(weeks)
    clean = ticker.strip().upper()
    if not clean:
        return _missing_buy_strength_assessment("", "", "Ticker fehlt.", window_days=window_days)

    row = _find_open_position_row(clean)
    if row is None:
        return _missing_buy_strength_assessment(clean, clean, "Keine offene Portfolio-Position gefunden.", window_days=window_days)

    row = _normalize_trade_republic_row_to_usd(row)
    if row.buy_date is None:
        return _missing_buy_strength_assessment(
            row.ticker,
            row.name,
            "Kein Kaufdatum gespeichert. Trage ein Kaufdatum ein oder importiere ein Depot mit Kaufdatum.",
            entry_price=row.entry_price,
            current_price=row.current_price,
            window_days=window_days,
        )

    start_date = row.buy_date - timedelta(days=90)
    try:
        price_rows = prices_repository.list_price_bars(row.ticker, start_date=start_date)
    except PriceRepositoryUnavailable:
        price_rows = []
    frame = _price_frame_from_rows(price_rows)
    if frame.empty:
        return _missing_buy_strength_assessment(
            row.ticker,
            row.name,
            "Keine Kursdaten im Price Cache. Starte Smart Refresh oder Kursdaten für diese Aktie.",
            buy_date=row.buy_date,
            entry_price=row.entry_price,
            current_price=row.current_price,
            window_days=window_days,
        )

    analysis_end = row.buy_date + timedelta(days=window_days)
    after_buy = frame[(frame.index.date >= row.buy_date) & (frame.index.date <= analysis_end)]
    if after_buy.empty:
        return _missing_buy_strength_assessment(
            row.ticker,
            row.name,
            f"Kursdaten liegen vor, aber nicht im gewählten Fenster von {weeks} Woche(n) ab Kaufdatum.",
            buy_date=row.buy_date,
            entry_price=row.entry_price,
            current_price=row.current_price,
            window_days=window_days,
        )

    try:
        rs_row = relative_strength_repository.get_latest_rs_rating(row.ticker)
    except RelativeStrengthRepositoryUnavailable:
        rs_row = None
    rs_frame = _rs_frame_from_metadata(rs_row.metadata_json if rs_row else {})

    return _evaluate_buy_strength(row, frame, rs_frame, window_days=window_days)


def _find_open_position_row(ticker: str) -> portfolio_repository.PortfolioPositionRow | None:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        return None
    clean = ticker.strip().upper()
    for row in rows:
        if row.ticker.strip().upper() == clean:
            return row
    return None


def _buy_strength_window_days(weeks: int) -> int:
    try:
        parsed = int(weeks)
    except (TypeError, ValueError):
        parsed = DEFAULT_BUY_STRENGTH_WEEKS
    parsed = max(1, min(6, parsed))
    return parsed * 7


def _evaluate_buy_strength(
    row: portfolio_repository.PortfolioPositionRow,
    frame: pd.DataFrame,
    rs_frame: pd.DataFrame,
    *,
    window_days: int,
) -> BuyStrengthAssessmentResponse:
    frame = frame.sort_index()
    analysis_end = row.buy_date + timedelta(days=window_days)
    analysis_frame = frame[frame.index.date <= analysis_end]
    if analysis_frame.empty:
        analysis_frame = frame
    after_buy = analysis_frame[(analysis_frame.index.date >= row.buy_date) & (analysis_frame.index.date <= analysis_end)]
    post_buy = after_buy.iloc[1:] if len(after_buy) > 1 else after_buy.iloc[0:0]
    latest = analysis_frame.iloc[-1]
    latest_date = pd.Timestamp(analysis_frame.index[-1]).date()
    buy_day = after_buy.iloc[0]
    before_buy = analysis_frame[analysis_frame.index < after_buy.index[0]]
    previous_day_low = _finite_float(before_buy["low"].iloc[-1]) if not before_buy.empty else None
    buy_day_low = _finite_float(buy_day["low"])
    latest_close = _finite_float(latest["close"])
    current_price = latest_close if latest_close is not None else row.current_price
    pnl_pct = (current_price / row.entry_price - 1) * 100 if row.entry_price and current_price else None

    close = analysis_frame["close"]
    volume = analysis_frame["volume"].fillna(0.0)
    ema21 = close.ewm(span=21, adjust=False, min_periods=5).mean()
    sma50 = close.rolling(50, min_periods=20).mean()
    close_range = _close_range(frame)
    pct = close.pct_change()

    analysis_rs_frame = _analysis_rs_frame(rs_frame, analysis_end)
    checks = [
        _check_immediate_strength(after_buy, row.entry_price, pnl_pct),
        _check_upper_candle_closes(after_buy),
        _check_rs_strength(analysis_rs_frame, row.buy_date),
        _check_rs_above_averages(analysis_rs_frame),
        _check_buy_low_not_undercut(after_buy, buy_day_low),
        _check_green_red_distribution(after_buy),
        _check_nearest_average_held(close, ema21, sma50),
    ]
    warnings = [
        _warning_high_volume_negatives(after_buy, buy_day),
        _warning_three_lower_lows(after_buy),
        _warning_average_break("break_ema21", "Bruch der 21-Tage-Linie", close, ema21),
        _warning_average_break("break_sma50", "Bruch der 50-Tage-Linie", close, sma50),
        _warning_close_below_buy_and_previous_low(latest_close, buy_day_low, previous_day_low),
        _warning_stall_days(post_buy, close_range, pct, volume),
        _warning_lower_range_closes(post_buy, close_range),
        _warning_down_volume_cluster(post_buy, pct, volume),
        _warning_rs_declines(analysis_rs_frame, row.buy_date),
        _warning_rs_breaks_averages(analysis_rs_frame),
        _warning_up_down_volume_deteriorates(analysis_frame, after_buy, row.buy_date),
    ]

    passed = sum(1 for check in checks if check.passed)
    active_warnings = sum(1 for check in warnings if not check.passed)
    status, status_label = _buy_strength_status(passed, len(checks), active_warnings)
    if status == "stark":
        message = "Frischer Kauf bestätigt Stärke, ohne auffällige Warnzeichen."
    elif status == "risk":
        message = "Nach dem Kauf häufen sich Warnzeichen. Position eng prüfen."
    elif status == "watch":
        message = "Stärke ist gemischt. Kursverhalten nach Kauf weiter beobachten."
    else:
        message = "Frischer Kauf ist auswertbar, aber noch nicht eindeutig stark."

    latest_lag = (date.today() - latest_date).days
    data_status = "fresh" if latest_lag <= 3 else "stale"
    return BuyStrengthAssessmentResponse(
        ticker=row.ticker,
        name=row.name,
        buy_date=row.buy_date.isoformat(),
        age_days=(date.today() - row.buy_date).days,
        window_days=window_days,
        source="database",
        data_status=data_status,
        status=status,
        status_label=status_label,
        message=message,
        entry_price=round(row.entry_price, 4),
        current_price=round(current_price, 4) if current_price is not None else None,
        pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
        buy_day_low=round(buy_day_low, 4) if buy_day_low is not None else None,
        previous_day_low=round(previous_day_low, 4) if previous_day_low is not None else None,
        latest_close=round(latest_close, 4) if latest_close is not None else None,
        latest_price_date=latest_date.isoformat(),
        checks=checks,
        warnings=warnings,
    )


def _missing_buy_strength_assessment(
    ticker: str,
    name: str,
    message: str,
    *,
    buy_date: date | None = None,
    entry_price: float | None = None,
    current_price: float | None = None,
    window_days: int = DEFAULT_BUY_STRENGTH_WEEKS * 7,
) -> BuyStrengthAssessmentResponse:
    return BuyStrengthAssessmentResponse(
        ticker=ticker,
        name=name or ticker,
        buy_date=buy_date.isoformat() if buy_date else None,
        age_days=(date.today() - buy_date).days if buy_date else None,
        window_days=window_days,
        source="missing",
        data_status="missing",
        status="missing",
        status_label="Nicht auswertbar",
        message=message,
        entry_price=entry_price,
        current_price=current_price,
        pnl_pct=(current_price / entry_price - 1) * 100 if entry_price and current_price else None,
    )


def _analysis_rs_frame(rs_frame: pd.DataFrame, analysis_end: date) -> pd.DataFrame:
    if rs_frame.empty:
        return rs_frame
    return rs_frame[rs_frame.index.date <= analysis_end]


def _price_frame_from_rows(rows: list[object]) -> pd.DataFrame:
    values: list[dict[str, object]] = []
    for row in rows:
        close_value = _finite_float(getattr(row, "close", None))
        if close_value is None:
            continue
        open_value = _finite_float(getattr(row, "open", None)) or close_value
        high_value = _finite_float(getattr(row, "high", None)) or max(open_value, close_value)
        low_value = _finite_float(getattr(row, "low", None)) or min(open_value, close_value)
        volume_value = _finite_float(getattr(row, "volume", None)) or 0.0
        values.append(
            {
                "date": pd.Timestamp(getattr(row, "date")),
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "volume": volume_value,
            }
        )
    if not values:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(values).set_index("date").sort_index()
    return frame[~frame.index.duplicated(keep="last")]


def _rs_frame_from_metadata(metadata: dict) -> pd.DataFrame:
    raw_history = metadata.get("rs_history") if isinstance(metadata, dict) else None
    if not isinstance(raw_history, list):
        return pd.DataFrame(columns=["rs", "rs_ema21", "rs_ema50"])
    values: list[dict[str, object]] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        rs_value = _finite_float(item.get("rs"))
        if rs_value is None:
            continue
        values.append(
            {
                "date": pd.Timestamp(item.get("date")),
                "rs": rs_value,
                "rs_ema21": _finite_float(item.get("rs_ema21")),
                "rs_ema50": _finite_float(item.get("rs_ema50")),
            }
        )
    if not values:
        return pd.DataFrame(columns=["rs", "rs_ema21", "rs_ema50"])
    frame = pd.DataFrame(values).set_index("date").sort_index()
    return frame[~frame.index.duplicated(keep="last")]


def _close_range(frame: pd.DataFrame) -> pd.Series:
    span = (frame["high"] - frame["low"]).replace(0, math.nan)
    return ((frame["close"] - frame["low"]) / span).fillna(0.5).clip(0, 1)


def _positive_check(key: str, label: str, passed: bool, detail: str, *, unavailable: bool = False) -> BuyStrengthCheck:
    return BuyStrengthCheck(
        key=key,
        label=label,
        category="positive",
        passed=passed,
        tone="neutral" if unavailable else ("good" if passed else "bad"),
        detail=detail,
    )


def _warning_check(key: str, label: str, active: bool, detail: str, *, unavailable: bool = False) -> BuyStrengthCheck:
    return BuyStrengthCheck(
        key=key,
        label=label,
        category="warning",
        passed=not active,
        tone="neutral" if unavailable else ("bad" if active else "good"),
        detail=detail,
    )


def _check_immediate_strength(after_buy: pd.DataFrame, entry_price: float, pnl_pct: float | None) -> BuyStrengthCheck:
    if after_buy.empty or not entry_price:
        return _positive_check("immediate_strength", "Unmittelbare Stärke nach Kauf", False, "Nicht genügend Daten.", unavailable=True)
    first_window = after_buy.head(min(5, len(after_buy)))
    max_first_close = float(first_window["close"].max())
    latest_close = float(after_buy["close"].iloc[-1])
    first_gain_pct = (max_first_close / entry_price - 1) * 100
    latest_gain_pct = (latest_close / entry_price - 1) * 100
    passed = first_gain_pct > 0 or latest_gain_pct > 0
    detail = f"Bestes frühes Close {first_gain_pct:+.1f}% vs. Einstand, aktuell {latest_gain_pct:+.1f}%."
    if pnl_pct is not None:
        detail = f"Aktueller P&L {pnl_pct:+.1f}%. " + detail
    return _positive_check("immediate_strength", "Unmittelbare Stärke nach Kauf", passed, detail)


def _check_upper_candle_closes(after_buy: pd.DataFrame) -> BuyStrengthCheck:
    if after_buy.empty:
        return _positive_check("upper_candle_closes", "Schlusskurse im oberen Kerzenbereich", False, "Nicht genügend Daten.", unavailable=True)
    ranges = _close_range(after_buy).head(min(5, len(after_buy)))
    upper_count = int((ranges >= 0.5).sum())
    ratio = upper_count / len(ranges) if len(ranges) else 0.0
    passed = ratio >= 0.6 and float(ranges.mean()) >= 0.5
    return _positive_check(
        "upper_candle_closes",
        "Schlusskurse im oberen Kerzenbereich",
        passed,
        f"{upper_count}/{len(ranges)} erste Handelstage schließen in der oberen Tageshälfte.",
    )


def _check_rs_strength(rs_frame: pd.DataFrame, buy_date: date) -> BuyStrengthCheck:
    if rs_frame.empty or "rs" not in rs_frame:
        return _positive_check("rs_new_high_or_rising", "Relative-Stärke-Linie steigt oder macht Hochs", False, "Keine RS-Historie gespeichert.", unavailable=True)
    after = rs_frame[rs_frame.index.date >= buy_date]
    if len(after) < 2:
        return _positive_check("rs_new_high_or_rising", "Relative-Stärke-Linie steigt oder macht Hochs", False, "Zu wenig RS-Punkte seit Kauf.", unavailable=True)
    latest = float(after["rs"].iloc[-1])
    previous = float(after["rs"].iloc[-2])
    previous_high = float(rs_frame["rs"].iloc[:-1].tail(63).max()) if len(rs_frame) > 1 else previous
    passed = latest >= previous or latest >= previous_high
    detail = f"RS aktuell {latest:.2f}, vorher {previous:.2f}, 63T-Hoch vor heute {previous_high:.2f}."
    return _positive_check("rs_new_high_or_rising", "Relative-Stärke-Linie steigt oder macht Hochs", passed, detail)


def _check_rs_above_averages(rs_frame: pd.DataFrame) -> BuyStrengthCheck:
    if rs_frame.empty:
        return _positive_check("rs_above_averages", "Relative Stärke über 21/50 EMA", False, "Keine RS-Historie gespeichert.", unavailable=True)
    latest = rs_frame.iloc[-1]
    rs = _finite_float(latest.get("rs"))
    rs_ema21 = _finite_float(latest.get("rs_ema21"))
    rs_ema50 = _finite_float(latest.get("rs_ema50"))
    if rs is None or rs_ema21 is None or rs_ema50 is None:
        return _positive_check("rs_above_averages", "Relative Stärke über 21/50 EMA", False, "RS-Durchschnitte fehlen.", unavailable=True)
    passed = rs >= rs_ema21 and rs >= rs_ema50
    return _positive_check(
        "rs_above_averages",
        "Relative Stärke über 21/50 EMA",
        passed,
        f"RS {rs:.2f}, 21 EMA {rs_ema21:.2f}, 50 EMA {rs_ema50:.2f}.",
    )


def _check_buy_low_not_undercut(after_buy: pd.DataFrame, buy_day_low: float | None) -> BuyStrengthCheck:
    if after_buy.empty or buy_day_low is None:
        return _positive_check("buy_day_low_held", "Tief des Kauftags hält", False, "Kauftag-Tief fehlt.", unavailable=True)
    min_low = float(after_buy["low"].min())
    passed = min_low >= buy_day_low * 0.999
    return _positive_check(
        "buy_day_low_held",
        "Tief des Kauftags hält",
        passed,
        f"Kauftag-Tief {buy_day_low:.2f}, tiefster Kurs seit Kauf {min_low:.2f}.",
    )


def _check_green_red_distribution(after_buy: pd.DataFrame) -> BuyStrengthCheck:
    if after_buy.empty:
        return _positive_check("green_red_distribution", "Grüne/rote Kerzen nach Kauf", False, "Nicht genügend Daten.", unavailable=True)
    green = int((after_buy["close"] >= after_buy["open"]).sum())
    red = len(after_buy) - green
    red_ratio = red / len(after_buy) if len(after_buy) else 1.0
    passed = red_ratio <= 0.30
    return _positive_check(
        "green_red_distribution",
        "Grüne/rote Kerzen nach Kauf",
        passed,
        f"{green} grüne und {red} rote Kerzen seit Kauf; Rot-Anteil {red_ratio * 100:.0f}%.",
    )


def _check_nearest_average_held(close: pd.Series, ema21: pd.Series, sma50: pd.Series) -> BuyStrengthCheck:
    latest_close = _finite_float(close.iloc[-1]) if not close.empty else None
    latest_ema21 = _finite_float(ema21.iloc[-1]) if not ema21.empty else None
    latest_sma50 = _finite_float(sma50.iloc[-1]) if not sma50.empty else None
    if latest_close is None or (latest_ema21 is None and latest_sma50 is None):
        return _positive_check("nearest_average_held", "Nähere 21/50-Tage-Linie hält", False, "Durchschnittsdaten fehlen.", unavailable=True)
    candidates = [(label, value) for label, value in (("21 EMA", latest_ema21), ("50 SMA", latest_sma50)) if value is not None]
    label, average = min(candidates, key=lambda item: abs(latest_close - item[1]))
    passed = latest_close >= average
    return _positive_check(
        "nearest_average_held",
        "Nähere 21/50-Tage-Linie hält",
        passed,
        f"Nähere Linie: {label} bei {average:.2f}; Schlusskurs {latest_close:.2f}.",
    )


def _warning_high_volume_negatives(after_buy: pd.DataFrame, buy_day: pd.Series) -> BuyStrengthCheck:
    if after_buy.empty:
        return _warning_check("more_negative_high_volume_days", "Mehr negative Hochvolumentage als positive", False, "Nicht genügend Daten.", unavailable=True)
    buy_volume = _finite_float(buy_day.get("volume")) or 0.0
    post = after_buy.iloc[1:] if len(after_buy) > 1 else after_buy.iloc[0:0]
    if post.empty or buy_volume <= 0:
        return _warning_check("more_negative_high_volume_days", "Mehr negative Hochvolumentage als positive", False, "Zu wenig Tage nach Kauf oder Kauftagsvolumen fehlt.", unavailable=True)
    high_volume = post["volume"] > buy_volume
    negative = int(((post["close"] < post["open"]) & high_volume).sum())
    positive = int(((post["close"] >= post["open"]) & high_volume).sum())
    active = negative > positive
    return _warning_check(
        "more_negative_high_volume_days",
        "Mehr negative Hochvolumentage als positive",
        active,
        f"{negative} negative vs. {positive} positive Tage mit Volumen über Kauftag.",
    )


def _warning_three_lower_lows(after_buy: pd.DataFrame) -> BuyStrengthCheck:
    lows = after_buy["low"].tolist()
    active = any(lows[idx] < lows[idx - 1] < lows[idx - 2] for idx in range(2, len(lows)))
    return _warning_check(
        "three_lower_lows",
        "Drei tiefere Tagestiefs in Folge",
        active,
        "Sequenz gefunden." if active else "Keine Serie aus drei tieferen Tagestiefs.",
    )


def _warning_average_break(key: str, label: str, close: pd.Series, average: pd.Series) -> BuyStrengthCheck:
    latest_close = _finite_float(close.iloc[-1]) if not close.empty else None
    latest_average = _finite_float(average.iloc[-1]) if not average.empty else None
    if latest_close is None or latest_average is None:
        return _warning_check(key, label, False, "Durchschnittsdaten fehlen.", unavailable=True)
    active = latest_close < latest_average
    return _warning_check(key, label, active, f"Schlusskurs {latest_close:.2f}, Linie {latest_average:.2f}.")


def _warning_close_below_buy_and_previous_low(
    latest_close: float | None,
    buy_day_low: float | None,
    previous_day_low: float | None,
) -> BuyStrengthCheck:
    if latest_close is None or buy_day_low is None or previous_day_low is None:
        return _warning_check("close_below_buy_and_previous_low", "Schluss unter Kauftag- und Vortagstief", False, "Kauftag- oder Vortagstief fehlt.", unavailable=True)
    active = latest_close < buy_day_low and latest_close < previous_day_low
    return _warning_check(
        "close_below_buy_and_previous_low",
        "Schluss unter Kauftag- und Vortagstief",
        active,
        f"Schluss {latest_close:.2f}, Kauftag-Tief {buy_day_low:.2f}, Vortagstief {previous_day_low:.2f}.",
    )


def _warning_stall_days(post_buy: pd.DataFrame, close_range: pd.Series, pct: pd.Series, volume: pd.Series) -> BuyStrengthCheck:
    if post_buy.empty:
        return _warning_check("stall_days_after_buy", "Stau-Tage nach Kauf", False, "Noch keine Handelstage nach dem Kauftag.", unavailable=True)
    aligned_range = close_range.reindex(post_buy.index)
    aligned_pct = pct.reindex(post_buy.index)
    aligned_volume = volume.reindex(post_buy.index)
    previous_volume = volume.shift(1).reindex(post_buy.index)
    stall = (aligned_pct.abs() <= 0.005) & (aligned_volume >= previous_volume * 0.95) & (aligned_range < 0.5)
    count = int(stall.fillna(False).sum())
    active = count >= 2
    return _warning_check("stall_days_after_buy", "Stau-Tage nach Kauf", active, f"{count} Stau-Tag(e) seit Kauf.")


def _warning_lower_range_closes(post_buy: pd.DataFrame, close_range: pd.Series) -> BuyStrengthCheck:
    if post_buy.empty:
        return _warning_check("lower_range_close_streak", "Mehrere Schlusskurse im unteren Kerzenbereich", False, "Noch keine Handelstage nach dem Kauftag.", unavailable=True)
    flags = (close_range.reindex(post_buy.index) <= 0.35).fillna(False).tolist()
    streak = _max_true_streak(flags)
    active = streak >= 3
    return _warning_check(
        "lower_range_close_streak",
        "Mehrere Schlusskurse im unteren Kerzenbereich",
        active,
        f"Maximale Serie: {streak} Tag(e) mit Schluss im unteren Kerzenbereich.",
    )


def _warning_down_volume_cluster(post_buy: pd.DataFrame, pct: pd.Series, volume: pd.Series) -> BuyStrengthCheck:
    if post_buy.empty:
        return _warning_check("down_volume_cluster", "Häufung negativer Tage mit erhöhtem Volumen", False, "Noch keine Handelstage nach dem Kauftag.", unavailable=True)
    vol_sma50 = volume.rolling(50, min_periods=10).mean()
    aligned_pct = pct.reindex(post_buy.index)
    aligned_volume = volume.reindex(post_buy.index)
    previous_volume = volume.shift(1).reindex(post_buy.index)
    average_volume = vol_sma50.reindex(post_buy.index)
    flags = (aligned_pct < 0) & ((aligned_volume > previous_volume) | (aligned_volume > average_volume))
    count = int(flags.fillna(False).sum())
    active = count >= 3
    return _warning_check(
        "down_volume_cluster",
        "Häufung negativer Tage mit erhöhtem Volumen",
        active,
        f"{count} negativer Tag(e) mit Volumen über Vortag oder Schnitt.",
    )


def _warning_rs_declines(rs_frame: pd.DataFrame, buy_date: date) -> BuyStrengthCheck:
    if rs_frame.empty or "rs" not in rs_frame:
        return _warning_check("rs_declines", "Relative-Stärke-Linie sinkt", False, "Keine RS-Historie gespeichert.", unavailable=True)
    after = rs_frame[rs_frame.index.date >= buy_date]
    if len(after) < 2:
        return _warning_check("rs_declines", "Relative-Stärke-Linie sinkt", False, "Zu wenig RS-Punkte seit Kauf.", unavailable=True)
    latest = float(after["rs"].iloc[-1])
    first = float(after["rs"].iloc[0])
    previous = float(after["rs"].iloc[-2])
    active = latest < first and latest < previous
    return _warning_check("rs_declines", "Relative-Stärke-Linie sinkt", active, f"RS Start {first:.2f}, vorher {previous:.2f}, aktuell {latest:.2f}.")


def _warning_rs_breaks_averages(rs_frame: pd.DataFrame) -> BuyStrengthCheck:
    if rs_frame.empty:
        return _warning_check("rs_breaks_averages", "Relative Stärke unter gleitenden Durchschnitten", False, "Keine RS-Historie gespeichert.", unavailable=True)
    latest = rs_frame.iloc[-1]
    rs = _finite_float(latest.get("rs"))
    rs_ema21 = _finite_float(latest.get("rs_ema21"))
    rs_ema50 = _finite_float(latest.get("rs_ema50"))
    if rs is None or rs_ema21 is None or rs_ema50 is None:
        return _warning_check("rs_breaks_averages", "Relative Stärke unter gleitenden Durchschnitten", False, "RS-Durchschnitte fehlen.", unavailable=True)
    active = rs < rs_ema21 or rs < rs_ema50
    return _warning_check(
        "rs_breaks_averages",
        "Relative Stärke unter gleitenden Durchschnitten",
        active,
        f"RS {rs:.2f}, 21 EMA {rs_ema21:.2f}, 50 EMA {rs_ema50:.2f}.",
    )


def _warning_up_down_volume_deteriorates(frame: pd.DataFrame, after_buy: pd.DataFrame, buy_date: date) -> BuyStrengthCheck:
    pct = frame["close"].pct_change()
    before = frame[frame.index.date < buy_date].tail(20)
    after = after_buy.tail(20)
    after_ratio = _up_down_volume_ratio(after, pct)
    before_ratio = _up_down_volume_ratio(before, pct)
    if after_ratio is None:
        return _warning_check("up_down_volume_deteriorates", "Up/Down-Volume-Ratio verschlechtert sich", False, "Nicht genügend Volumendaten.", unavailable=True)
    active = after_ratio < 1.0
    detail = f"Nach Kauf {after_ratio:.2f}."
    if before_ratio is not None:
        active = after_ratio < before_ratio * 0.8 or after_ratio < 1.0
        detail = f"Vor Kauf {before_ratio:.2f}, nach Kauf {after_ratio:.2f}."
    return _warning_check("up_down_volume_deteriorates", "Up/Down-Volume-Ratio verschlechtert sich", active, detail)


def _up_down_volume_ratio(window: pd.DataFrame, pct: pd.Series) -> float | None:
    if window.empty:
        return None
    aligned_pct = pct.reindex(window.index)
    up_volume = float(window.loc[aligned_pct > 0, "volume"].sum())
    down_volume = float(window.loc[aligned_pct < 0, "volume"].sum())
    if down_volume <= 0:
        return None if up_volume <= 0 else 99.0
    return up_volume / down_volume


def _max_true_streak(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _buy_strength_status(passed: int, total: int, active_warnings: int) -> tuple[str, str]:
    if total <= 0:
        return "missing", "Nicht auswertbar"
    if active_warnings >= 4:
        return "risk", "Risiko"
    if active_warnings >= 2:
        return "watch", "Beobachten"
    if passed >= max(5, math.ceil(total * 0.7)) and active_warnings <= 1:
        return "stark", "Stark"
    return "ok", "Neutral"


def _empty_portfolio_snapshot() -> PortfolioSnapshotResponse:
    try:
        cash = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable:
        cash = 0.0
    cash_ratio = 100.0 if cash > 0 else 0.0
    return PortfolioSnapshotResponse(
        as_of=datetime.now(UTC).isoformat(),
        total_value=cash,
        invested_value=0.0,
        cash_balance=cash,
        cash_ratio_pct=cash_ratio,
        portfolio_atr_pct=0.0,
        market_atr_pct=_market_atr_pct(),
        beta_balancer=1.0,
        max_depot_loss_abs=None,
        max_depot_loss_available=False,
        max_depot_loss_pct=0.0,
        kpis=[
            KpiCard(
                label="Depotwert",
                value=f"{cash:,.0f} EUR",
                detail="kein Depot importiert",
                tone="neutral",
            ),
            KpiCard(label="Positionen", value="0", detail="Import offen", tone="warning"),
            KpiCard(label="Unrealisiert", value="+0 EUR", detail="keine offenen Positionen", tone="neutral"),
            KpiCard(label="Cashquote", value=f"{cash_ratio:.1f}%", detail=f"{cash:,.0f} EUR", tone="neutral"),
            KpiCard(label="Portfolio ATR", value="0.00%", detail="keine offenen Positionen", tone="neutral"),
        ],
        positions=[],
    )


def get_portfolio_curve(days: int = DEFAULT_PORTFOLIO_CURVE_DAYS, start_date: date | None = None) -> PortfolioCurveResponse:
    curve_start = _portfolio_curve_start_date(days=days, start_date=start_date)
    tr_error: str | None = None
    try:
        tr_curve = _get_trade_republic_curve(days=days, start_date=curve_start)
    except Exception as exc:
        tr_curve = None
        tr_error = f" TR-Kurve: {exc}"
    if tr_curve is not None:
        return tr_curve

    try:
        rows = portfolio_repository.list_open_positions()
        cash = portfolio_repository.get_cash_balance()
    except PortfolioRepositoryUnavailable as exc:
        return _missing_portfolio_curve(f"Portfolio-Datenbank ist nicht erreichbar: {exc}.{tr_error or ''}")
    if not rows:
        return _missing_portfolio_curve(f"Keine offenen Positionen für die Depotkurve.{tr_error or ''}")
    rows = [_normalize_trade_republic_row_to_usd(row) for row in rows]
    if rows and all(row.currency == "USD" for row in rows):
        fx_rate = get_eur_usd_rate()
        cash = round(float(eur_to_usd(cash, rate=fx_rate) or 0.0), 2)

    price_start_date = curve_start - timedelta(days=10)
    series_map: dict[str, pd.Series] = {}
    for row in rows:
        try:
            price_rows = prices_repository.list_price_bars(row.ticker, start_date=price_start_date)
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
        return _missing_portfolio_curve(f"Für die offenen Positionen fehlen Price-Bars im Cache.{tr_error or ''}")

    all_cached_dates = sorted(set().union(*(series.index for series in series_map.values())))
    all_dates = sorted(date_value for date_value in all_cached_dates if date_value.date() >= curve_start)
    used_requested_start = True
    if not all_dates:
        all_dates = all_cached_dates
        used_requested_start = False
    frame = pd.DataFrame(index=pd.DatetimeIndex(all_dates))
    if frame.empty:
        return _missing_portfolio_curve(f"Für die offenen Positionen fehlen Price-Bars im Cache.{tr_error or ''}")
    for row in rows:
        series = series_map.get(row.ticker)
        if series is None:
            continue
        frame[row.ticker] = series.reindex(frame.index).ffill()
    benchmark_index = _benchmark_index_series(frame.index)

    points: list[PortfolioCurvePoint] = []
    index_values: list[float] = []
    for timestamp, values in frame.iterrows():
        positions_value = 0.0
        for row in rows:
            close = values.get(row.ticker)
            if _is_finite_number(close):
                positions_value += float(close) * row.shares
        depot_value = positions_value + cash
        if not math.isfinite(depot_value) or depot_value <= 0:
            continue
        if not index_values:
            base = depot_value
        portfolio_index = depot_value / base * 100
        if not math.isfinite(portfolio_index):
            continue
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
                sp500_index=_rounded_series_value(benchmark_index, timestamp),
            )
        )

    if not points:
        return _missing_portfolio_curve(f"Depotkurve konnte aus vorhandenen Positionen nicht berechnet werden.{tr_error or ''}")

    return PortfolioCurveResponse(
        as_of=points[-1].date if points else datetime.now(UTC).date().isoformat(),
        source="database",
        data_status="fresh",
        base_date=points[0].date if points else curve_start.isoformat(),
        message=(
            "Depotkurve aus offenen Positionen, Price Cache und Cash-Bestand."
            if used_requested_start
            else f"Keine Price-Bars ab {curve_start.isoformat()} gefunden; Kurve startet mit dem ersten verfügbaren Cache-Datum."
        ),
        points=points,
    )


def _missing_portfolio_curve(message: str) -> PortfolioCurveResponse:
    return PortfolioCurveResponse(
        as_of=datetime.now(UTC).date().isoformat(),
        source="missing",
        data_status="missing",
        base_date=None,
        message=message.strip(),
        points=[],
    )


def _get_trade_republic_curve(days: int, start_date: date) -> PortfolioCurveResponse | None:
    try:
        transactions = portfolio_repository.list_trade_republic_transactions()
    except PortfolioRepositoryUnavailable:
        return None
    if not transactions:
        return None
    fx_rate = get_eur_usd_rate()

    curve_start_date = start_date
    first_transaction_date = min(row.date for row in transactions)
    end_date = date.today()
    if first_transaction_date > end_date or curve_start_date > end_date:
        return None
    calendar = pd.DatetimeIndex(pd.date_range(first_transaction_date, end_date, freq="B"))
    if calendar.empty:
        return None

    positions_value = pd.Series(0.0, index=calendar)
    missing_price_instruments: list[str] = []
    trade_price_fallbacks: list[str] = []

    for instrument_key, instrument_transactions in _trade_republic_valuation_groups(transactions).items():
        ticker = instrument_transactions[0].ticker
        label = ticker or instrument_key
        shares = pd.Series(0.0, index=calendar)
        running = 0.0
        for row in sorted(instrument_transactions, key=_stored_transaction_sort_key):
            typ = normalize_transaction_type(row.transaction_type)
            if typ == "split":
                running = max(row.shares, 0.0)
            elif typ in SHARE_DECREASE_TYPES and abs(float(row.shares or 0.0)) <= 1e-12 and row.asset_class.upper() == "DERIVATIVE":
                running = 0.0
            elif typ in NON_SHARE_TYPES:
                pass
            else:
                running = max(running + _signed_share_delta(typ, row.shares), 0.0)
            shares.loc[shares.index >= pd.Timestamp(row.date)] = running

        cached_prices = _cached_price_series(ticker, first_transaction_date) if ticker else pd.Series(dtype=float)
        if cached_prices.empty:
            cached_prices = _trade_price_fallback_series(instrument_transactions, calendar, fx_rate=fx_rate)
            if cached_prices.empty:
                missing_price_instruments.append(label)
                continue
            trade_price_fallbacks.append(label)
        aligned_prices = _align_price_series_to_calendar(cached_prices, calendar)
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
        cash_daily.loc[day] += _money_to_usd(row.net_amount, row.currency, fx_rate)
        transaction_type = normalize_transaction_type(row.transaction_type)
        if transaction_type in TR_EXTERNAL_FLOW_TYPES:
            external_daily.loc[day] += _money_to_usd(row.net_amount, row.currency, fx_rate)
        elif transaction_type in {"transfer_in", "transfer_out"}:
            external_daily.loc[day] += _transfer_external_value(row, fx_rate)

    curve = pd.DataFrame(
        {
            "date": calendar,
            "positions_value": positions_value.values,
            "cash": cash_daily.cumsum().values,
            "external_flow": external_daily.values,
        }
    )
    curve["depot_value"] = curve["positions_value"] + curve["cash"]
    first_active = curve["positions_value"].abs().gt(1e-9)
    if not first_active.any():
        first_active = curve["depot_value"].abs().gt(1e-9)
    if not first_active.any():
        return None
    curve = curve.loc[first_active.idxmax() :].reset_index(drop=True)

    window_start = pd.Timestamp(curve_start_date)
    curve = curve[curve["date"] >= window_start].reset_index(drop=True)
    if curve.empty:
        window_start = pd.Timestamp(max(first_transaction_date, date.today() - timedelta(days=max(30, min(2500, days)))))
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
        daily_return = (current - previous - external) / previous if previous > 0 and math.isfinite(previous) else 0.0
        next_index = index_values[-1] * (1.0 + daily_return)
        index_values.append(next_index if math.isfinite(next_index) else index_values[-1])
    curve["portfolio_index"] = index_values
    first_index = _finite_float(curve["portfolio_index"].iloc[0])
    if first_index and first_index > 0:
        curve["portfolio_index"] = curve["portfolio_index"] / first_index * 100
    curve["portfolio_index_sma10"] = curve["portfolio_index"].rolling(10, min_periods=10).mean()
    curve["portfolio_index_sma21"] = curve["portfolio_index"].rolling(21, min_periods=21).mean()
    benchmark_index = _benchmark_index_series(pd.DatetimeIndex(curve["date"]))
    curve["sp500_index"] = benchmark_index.reindex(pd.DatetimeIndex(curve["date"])).values

    points: list[PortfolioCurvePoint] = []
    for row in curve.itertuples():
        depot_value = _finite_float(row.depot_value)
        positions_value_row = _finite_float(row.positions_value)
        cash_value = _finite_float(row.cash)
        portfolio_index = _finite_float(row.portfolio_index)
        if depot_value is None or positions_value_row is None or cash_value is None or portfolio_index is None:
            continue
        points.append(
            PortfolioCurvePoint(
                date=pd.Timestamp(row.date).date().isoformat(),
                depot_value=round(depot_value, 2),
                positions_value=round(positions_value_row, 2),
                cash=round(cash_value, 2),
                portfolio_index=round(portfolio_index, 2),
                portfolio_index_sma10=_round_optional(row.portfolio_index_sma10, 2),
                portfolio_index_sma21=_round_optional(row.portfolio_index_sma21, 2),
                sp500_index=_round_optional(row.sp500_index, 2),
            )
        )
    if not points:
        return None
    details = []
    if trade_price_fallbacks:
        details.append(f"Trade-Price-Fallback für {len(trade_price_fallbacks)} Instrumente")
    if missing_price_instruments:
        details.append(f"Kursdaten fehlen für {len(missing_price_instruments)} Instrumente")
    message = f"Depotkurve aus gespeichertem Trade-Republic-Transaktionsexport, TR-EUR-Werte mit EUR/USD {fx_rate.rate:.4f} in USD umgerechnet."
    if details:
        message += " " + " · ".join(details)

    return PortfolioCurveResponse(
        as_of=points[-1].date if points else datetime.now(UTC).date().isoformat(),
        source="trade_republic_transactions",
        data_status="fresh" if points else "missing",
        base_date=points[0].date if points else curve_start_date.isoformat(),
        message=message,
        points=points,
    )


def _portfolio_curve_start_date(days: int, start_date: date | None) -> date:
    if start_date is not None:
        return start_date
    if days != DEFAULT_PORTFOLIO_CURVE_DAYS:
        return date.today() - timedelta(days=max(30, min(2500, days)))
    today = date.today()
    return date(today.year, 1, 1)


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
    ).pipe(_deduplicate_series_index)


def _benchmark_index_series(calendar: pd.DatetimeIndex) -> pd.Series:
    if calendar.empty:
        return pd.Series(dtype=float)
    start = pd.Timestamp(calendar.min()).date()
    for ticker in ("^GSPC", "SPY"):
        series = _cached_price_series(ticker, start)
        if not series.empty:
            aligned = _align_price_series_to_calendar(series, calendar)
            valid = aligned.dropna()
            if not valid.empty and float(valid.iloc[0]) > 0:
                return aligned / float(valid.iloc[0]) * 100
    return pd.Series(index=calendar, dtype=float)


def _rounded_series_value(series: pd.Series, timestamp: pd.Timestamp) -> float | None:
    if series.empty or timestamp not in series.index:
        return None
    value = series.loc[timestamp]
    return _round_optional(value, 2)


def _round_optional(value: object, digits: int) -> float | None:
    parsed = _finite_float(value)
    return round(parsed, digits) if parsed is not None else None


def _finite_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _is_finite_number(value: object) -> bool:
    return _finite_float(value) is not None


def _trade_price_fallback_series(
    transactions: list[portfolio_repository.TradeRepublicStoredTransactionRow],
    calendar: pd.DatetimeIndex,
    *,
    fx_rate: FxRate | None = None,
) -> pd.Series:
    rate = fx_rate or get_eur_usd_rate()
    values = [
        (pd.Timestamp(row.date), _money_to_usd(float(row.price), row.currency, rate))
        for row in transactions
        if row.price is not None
        and row.price > 0
        and normalize_transaction_type(row.transaction_type) in {"buy", "sell", "transfer_in", "sell_cancelled", "warrant_exercise", "expiration", "delisted"}
    ]
    if not values:
        return pd.Series(dtype=float)
    series = pd.Series(
        [item[1] for item in values],
        index=pd.DatetimeIndex([item[0] for item in values]),
        dtype=float,
    ).pipe(_deduplicate_series_index)
    return _align_price_series_to_calendar(series, calendar)


def _deduplicate_series_index(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    ordered = series.sort_index()
    if not ordered.index.has_duplicates:
        return ordered
    return ordered[~ordered.index.duplicated(keep="last")]


def _align_price_series_to_calendar(series: pd.Series, calendar: pd.DatetimeIndex) -> pd.Series:
    if calendar.empty:
        return pd.Series(dtype=float)
    clean = _deduplicate_series_index(series)
    if clean.empty:
        return pd.Series(0.0, index=calendar, dtype=float)
    return clean.reindex(calendar, method="ffill").ffill().bfill().fillna(0.0)


def _signed_share_delta(transaction_type: str, shares: float) -> float:
    transaction_type = normalize_transaction_type(transaction_type)
    amount = abs(float(shares or 0.0))
    if transaction_type in SHARE_DECREASE_TYPES:
        return -amount
    if transaction_type in SHARE_INCREASE_TYPES:
        return amount
    return 0.0


def _trade_republic_valuation_groups(
    transactions: list[portfolio_repository.TradeRepublicStoredTransactionRow],
) -> dict[str, list[portfolio_repository.TradeRepublicStoredTransactionRow]]:
    groups: dict[str, list[portfolio_repository.TradeRepublicStoredTransactionRow]] = {}
    for row in transactions:
        ticker = str(row.ticker or "").upper().strip()
        isin = row.isin or str((row.raw_json or {}).get("isin") or "").upper().strip()
        asset_class = (row.asset_class or str((row.raw_json or {}).get("asset_class") or "")).upper().strip()
        key = ticker or (isin if asset_class == "DERIVATIVE" else "")
        if not key:
            continue
        groups.setdefault(key, []).append(row)
    return groups


def _stored_transaction_sort_key(row: portfolio_repository.TradeRepublicStoredTransactionRow) -> tuple[pd.Timestamp, str]:
    raw = row.raw_json or {}
    raw_ts = raw.get("event_ts") or raw.get("datetime") or row.date
    try:
        timestamp = pd.Timestamp(raw_ts)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert(None)
    except Exception:
        timestamp = pd.Timestamp(row.date)
    return timestamp, str(raw.get("transaction_id") or raw.get("external_id") or "")


def calculate_position_size(payload: PortfolioPositionSizeRequest) -> PortfolioPositionSizeResponse:
    risk_budget = payload.depot_value * (payload.risk_per_position_pct / 100)
    if payload.stop_unit == "usd" and payload.stop_amount:
        risk_per_share = payload.stop_amount
        stop_price = max(payload.buy_price - payload.stop_amount, 0.0)
    else:
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

    balancer_score = _beta_balancer_score(
        beta=payload.beta,
        atr_pct=payload.atr_pct,
        market_atr_pct=payload.market_atr_pct,
    )
    if balancer_score is not None and balancer_score > 0:
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
        stop_price=payload.stop_price,
        broker=payload.broker,
        account=payload.account,
        note=payload.note,
        record_transaction=payload.record_transaction,
    )
    row = portfolio_repository.upsert_position(write)
    return PortfolioPositionWriteResponse(position=_position_from_row(row, invested=row.current_price * row.shares))


def update_portfolio_position_stop(ticker: str, payload: PortfolioPositionStopRequest) -> PortfolioPositionWriteResponse:
    row = portfolio_repository.update_position_stop_price(ticker, payload.stop_price)
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
    fx_rate = get_eur_usd_rate()
    normalized_reconstructed = _trade_republic_positions_to_usd(reconstructed, fx_rate)
    converted_isins = {item.isin for item in reconstructed if str(item.currency or "").upper() == "EUR"}
    open_mapping_isins = {item.isin for item in reconstructed}
    open_mapping_isins.update(item.isin for item in skipped if item.asset_class in POSITION_ASSET_CLASSES)
    response_diagnostics = [
        item
        for item in diagnostics
        if str(item.get("isin") or "").upper() in open_mapping_isins
    ]
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
            note=_trade_republic_import_note(item.isin, fx_rate=fx_rate, converted=item.isin in converted_isins),
            warnings=[],
        )
        for item in normalized_reconstructed
    ]
    mappings = [
        TradeRepublicIsinMappingItem(
            isin=str(item["isin"]),
            name=str(item["name"]),
            asset_class=str(item["asset_class"]),
            ticker=str(item["ticker"] or ""),
            source=item["source"],
        )
        for item in response_diagnostics
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
    if converted_isins:
        warnings.append(
            f"TR-EUR-Preise wurden automatisch mit EUR/USD {fx_rate.rate:.4f} ({fx_rate.source}, {fx_rate.as_of.isoformat()}) in USD umgerechnet."
        )

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
        positions=normalized_reconstructed,
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


def get_isin_mappings() -> IsinMappingListResponse:
    try:
        rows = portfolio_repository.list_isin_mapping_rows()
    except PortfolioRepositoryUnavailable:
        rows = []
    return IsinMappingListResponse(
        mappings=[
            TradeRepublicIsinMappingItem(
                isin=row.isin,
                name="",
                asset_class="",
                ticker=row.ticker,
                source="saved" if row.source != "manual" else "manual",
            )
            for row in rows
        ]
    )


def update_isin_mappings(payload: IsinMappingPatchRequest) -> IsinMappingListResponse:
    mapping_dict = {
        item.isin.upper().strip(): item.ticker.upper().strip()
        for item in payload.mappings
        if item.isin.strip() and item.ticker.strip()
    }
    rows = portfolio_repository.upsert_isin_mappings(mapping_dict, source="manual")
    return IsinMappingListResponse(
        mappings=[
            TradeRepublicIsinMappingItem(
                isin=row.isin,
                name="",
                asset_class="",
                ticker=row.ticker,
                source="manual" if row.source == "manual" else "saved",
            )
            for row in rows
        ]
    )


def _position_from_row(row: portfolio_repository.PortfolioPositionRow, *, invested: float) -> PortfolioPosition:
    row = _normalize_trade_republic_row_to_usd(row)
    market_value = row.current_price * row.shares
    pnl_pct = (row.current_price / row.entry_price - 1) * 100 if row.entry_price else 0
    pnl_abs = (row.current_price - row.entry_price) * row.shares if row.entry_price else 0
    atr_pct = _atr_pct_for_ticker(row.ticker)
    beta = _beta_for_ticker(row.ticker)
    weight_pct = market_value / invested * 100 if invested else 100
    market_atr_pct = _market_atr_pct()
    beta_balancer_score = _beta_balancer_score(beta=beta, atr_pct=atr_pct, market_atr_pct=market_atr_pct)
    position_loss_risk = _position_loss_risk(row)
    return PortfolioPosition(
        ticker=row.ticker,
        name=row.name,
        shares=row.shares,
        entry_price=row.entry_price,
        current_price=row.current_price,
        market_value=market_value,
        pnl_pct=pnl_pct,
        weight_pct=weight_pct,
        atr_pct=atr_pct,
        beta=beta,
        beta_balancer_score=beta_balancer_score,
        risk_contribution=_risk_contribution(weight_pct=weight_pct, beta_balancer_score=beta_balancer_score),
        position_loss_risk=position_loss_risk,
        position_loss_risk_pct=position_loss_risk / invested * 100 if invested and position_loss_risk is not None else None,
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


def _trade_republic_positions_to_usd(
    positions: list[DomainTradeRepublicPosition],
    fx_rate: FxRate,
) -> list[DomainTradeRepublicPosition]:
    normalized: list[DomainTradeRepublicPosition] = []
    for item in positions:
        if str(item.currency or "").upper() != "EUR":
            normalized.append(item)
            continue
        normalized.append(
            DomainTradeRepublicPosition(
                isin=item.isin,
                ticker=item.ticker,
                name=item.name,
                shares=item.shares,
                avg_buy_price=round(float(eur_to_usd(item.avg_buy_price, rate=fx_rate) or 0.0), 6),
                first_buy_date=item.first_buy_date,
                currency="USD",
                asset_class=item.asset_class,
            )
        )
    return normalized


def _trade_republic_import_note(isin: str, *, fx_rate: FxRate, converted: bool) -> str:
    note = f"TR-Transaktionsimport / ISIN {isin}"
    if converted:
        note += f" / EUR-Preise mit EUR/USD {fx_rate.rate:.4f} nach USD umgerechnet"
    return note


def _normalize_trade_republic_row_to_usd(
    row: portfolio_repository.PortfolioPositionRow,
    *,
    fx_rate: FxRate | None = None,
) -> portfolio_repository.PortfolioPositionRow:
    if "trade republic" not in str(row.broker or "").lower() or str(row.currency or "").upper() != "EUR":
        return row
    rate = fx_rate or get_eur_usd_rate()
    entry_price = float(eur_to_usd(row.entry_price, rate=rate) or row.entry_price)
    current_price = row.current_price
    if row.current_price_source != "price_cache":
        current_price = float(eur_to_usd(row.current_price, rate=rate) or row.current_price)
    stop_price = float(eur_to_usd(row.stop_price, rate=rate)) if row.stop_price is not None else None
    return portfolio_repository.PortfolioPositionRow(
        ticker=row.ticker,
        name=row.name,
        shares=row.shares,
        entry_price=round(entry_price, 6),
        current_price=round(float(current_price), 6),
        currency="USD",
        buy_date=row.buy_date,
        pivot_tag=row.pivot_tag,
        stop_pct=row.stop_pct,
        stop_price=round(stop_price, 6) if stop_price is not None else None,
        broker=row.broker,
        account=row.account,
        note=row.note,
        current_price_source=row.current_price_source,
    )


def _money_to_usd(value: float, currency: str, fx_rate: FxRate) -> float:
    if str(currency or "").upper() == "EUR":
        return float(eur_to_usd(value, rate=fx_rate) or 0.0)
    return float(value or 0.0)


def _transfer_external_value(row: portfolio_repository.TradeRepublicStoredTransactionRow, fx_rate: FxRate) -> float:
    transaction_type = normalize_transaction_type(row.transaction_type)
    shares = abs(float(row.shares or 0.0))
    price = float(row.price or 0.0)
    if shares <= 0 or price <= 0:
        return 0.0
    value = _money_to_usd(shares * price, row.currency, fx_rate)
    return -value if transaction_type == "transfer_out" else value


def _portfolio_display_currency(positions: list[PortfolioPosition]) -> str:
    if positions and all(position.currency == "USD" for position in positions):
        return "USD"
    return "EUR"


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


def _market_atr_pct() -> float | None:
    for ticker in ("^GSPC", "SPY"):
        atr_pct = _atr_pct_for_ticker(ticker)
        if atr_pct > 0:
            return atr_pct
    return None


def _beta_for_ticker(ticker: str) -> float:
    try:
        snapshot = fundamentals_repository.get_latest_fundamentals(ticker)
    except FundamentalsRepositoryUnavailable:
        snapshot = None
    beta = _finite_float(snapshot.beta) if snapshot is not None else None
    return round(beta, 4) if beta is not None and beta > 0 else 1.0


def _beta_balancer_score(*, beta: float | None, atr_pct: float | None, market_atr_pct: float | None) -> float | None:
    beta_value = _finite_float(beta)
    atr_value = _finite_float(atr_pct)
    market_atr_value = _finite_float(market_atr_pct)
    if beta_value is None or atr_value is None or market_atr_value is None or market_atr_value <= 0:
        return None
    return round(0.60 * beta_value + 0.40 * (atr_value / market_atr_value), 4)


def _risk_contribution(*, weight_pct: float, beta_balancer_score: float | None) -> float | None:
    score = _finite_float(beta_balancer_score)
    if score is None:
        return None
    return round((weight_pct / 100) * score, 4)


def _position_loss_risk(row: portfolio_repository.PortfolioPositionRow) -> float | None:
    stop_price = _finite_float(row.stop_price)
    current_price = _finite_float(row.current_price)
    shares = _finite_float(row.shares)
    if stop_price is None or current_price is None or shares is None:
        return None
    loss_per_share = max(current_price - stop_price, 0.0)
    return round(loss_per_share * shares, 2)


def _tone_for_portfolio_atr(value: float) -> str:
    if value <= 0:
        return "neutral"
    if value <= 2.5:
        return "good"
    if value <= 4:
        return "neutral"
    if value <= 8:
        return "warning"
    return "bad"


def _portfolio_atr_detail(value: float) -> str:
    if value <= 0:
        return "ATR-Cache fehlt oder ist noch nicht berechnet"
    return "<=2,5 ruhig · 2,5-4 lebhaft · 4-8 stürmisch · >8 explosiv"


def _tone_for_portfolio_beta_balancer(value: float) -> str:
    if value <= 0:
        return "neutral"
    if value <= 1.0:
        return "good"
    if value <= 1.5:
        return "warning"
    return "bad"


def _tone_for_max_depot_loss(value: float) -> str:
    if value <= 8:
        return "good"
    if value <= 12:
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
