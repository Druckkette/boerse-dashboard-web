"""Portfolio attribution and risk from saved executions and observed prices only."""
from collections import defaultdict, OrderedDict
from threading import RLock
from time import monotonic
from datetime import date, timedelta
from math import isfinite
from bisect import bisect_right

import pandas as pd

from app.repositories import analysis as repository, prices, earnings, portfolio as portfolio_repository
from app.repositories.industry_group_rs import list_group_members
from app.domain.stocks.industry_groups import TAXONOMY_VERSION
from app.domain.portfolio.trade_republic import normalize_transaction_type
from app.services.fx import yahoo_quote_currency
from app.services.market_calendar import completed_us_market_session
from app.services.money import money_sum, rounded_money
from app.services.portfolio import get_portfolio_snapshot, SHARE_DECREASE_TYPES, SHARE_INCREASE_TYPES

EXTERNAL = {"deposit", "withdrawal", "cash_deposit", "cash_withdrawal", "customer_deposit", "customer_withdrawal",
            "customer_inbound", "customer_outbound", "customer_outbound_request", "customer_inpayment", "customer_outpayment",
            "pay_in", "pay_out", "inbound_payment", "outbound_payment", "transfer_inbound", "transfer_instant_inbound", "transfer_outbound", "gift"}


class PriceBook:
    def __init__(self, histories, currencies):
        self.points = {ticker: sorted({row.date: float(row.close) for row in rows if row.close is not None and isfinite(float(row.close)) and row.close > 0}.items()) for ticker, rows in histories.items()}
        self.dates = {ticker: [point[0] for point in rows] for ticker, rows in self.points.items()}
        self.currencies = currencies

    def close(self, ticker, day, *, exact=False):
        index = bisect_right(self.dates.get(ticker, []), day) - 1
        if index < 0:
            return None
        stamp, value = self.points[ticker][index]
        return value if (stamp == day if exact else (day - stamp).days <= 4) else None

    def fx(self, source, target, day, *, exact=False):
        source_minor, target_minor = source in {"GBp", "GBX"}, target in {"GBp", "GBX"}
        source, target = "GBP" if source_minor else source.upper(), "GBP" if target_minor else target.upper()
        scale = (0.01 if source_minor else 1) / (0.01 if target_minor else 1)
        if source == target:
            return scale
        left = 1.0 if source == "USD" else self.close(f"{source}USD=X", day, exact=exact)
        right = 1.0 if target == "USD" else self.close(f"{target}USD=X", day, exact=exact)
        return left / right * scale if left is not None and right is not None else None

    def value(self, ticker, quantity, day, base, *, exact=False):
        if abs(quantity) < 1e-9:
            return 0.0
        close = self.close(ticker, day, exact=exact)
        fx = self.fx(self.currencies.get(ticker, yahoo_quote_currency(ticker)), base, day, exact=exact)
        return quantity * close * fx if close is not None and fx is not None else None


def share_state(events, through):
    shares = defaultdict(float)
    for event in events:
        if event["date"] > through or not event.get("ticker"):
            continue
        ticker, kind = event["ticker"], normalize_transaction_type(event["kind"])
        quantity = abs(float(event.get("shares") or 0))
        if kind == "split":
            shares[ticker] = quantity
        elif kind in SHARE_INCREASE_TYPES:
            shares[ticker] += quantity
        elif kind in SHARE_DECREASE_TYPES:
            shares[ticker] -= quantity
    return dict(shares)


def attribution(ledger, book, *, start, end, base, positions):
    events = sorted([event for event in ledger["events"] if event["date"] <= end], key=lambda event: (event["date"], event.get("id", "")))
    opening, ending = share_state(events, start), share_state(events, end)
    actual = defaultdict(float)
    for position in positions:
        actual[position.ticker] += position.shares
    mismatches = sorted(ticker for ticker in set(actual) | set(ending) if abs(actual[ticker] - ending.get(ticker, 0)) > 1e-6)
    model = "executions" if events and not mismatches else "current_holdings"
    if model == "current_holdings":
        opening = ending = dict(actual)
    period = [event for event in events if start < event["date"] <= end]
    tickers = set(opening) | set(ending) | ({event["ticker"] for event in period if event.get("ticker")} if model == "executions" else set())
    rows = []
    for ticker in sorted(tickers):
        held_start, held_end = opening.get(ticker, 0), ending.get(ticker, 0)
        changes = [event for event in period if event.get("ticker") == ticker]
        if abs(held_start) < 1e-9 and abs(held_end) < 1e-9 and not changes:
            continue
        first, last = book.value(ticker, held_start, start, base), book.value(ticker, held_end, end, base)
        cash, costs, external, missing = [], [], [], first is None or last is None
        if model == "executions":
            for event in changes:
                kind = normalize_transaction_type(event["kind"])
                fx = book.fx(event["currency"], base, event["date"])
                if fx is None:
                    missing = True
                    continue
                if kind in {"transfer_in", "transfer_out"}:
                    value = book.value(ticker, abs(event.get("shares") or 0), event["date"], base)
                    if value is None:
                        missing = True
                    else:
                        external.append(value * (-1 if kind == "transfer_out" else 1))
                elif kind not in EXTERNAL:
                    cash.append(float(event.get("net") or 0) * fx)
                    costs.append((abs(event.get("fees") or 0) + abs(event.get("tax") or 0)) * fx)
        result = None if missing else last - first + money_sum(cash) - money_sum(external)
        # Attribution decomposition on observed opening exposure. Trading and
        # interaction effects stay explicit instead of being called pure FX.
        c0, c1 = book.close(ticker, start), book.close(ticker, end)
        currency = book.currencies.get(ticker, yahoo_quote_currency(ticker))
        f0, f1 = book.fx(currency, base, start), book.fx(currency, base, end)
        price_effect = held_start * (c1 - c0) * f0 if None not in (c0, c1, f0) else None
        fx_effect = held_start * c0 * (f1 - f0) if None not in (c0, f0, f1) else None
        residual = result - price_effect - fx_effect + money_sum(costs) if None not in (result, price_effect, fx_effect) else None
        rows.append(dict(ticker=ticker, result=rounded_money(result) if result is not None else None,
            price_effect=rounded_money(price_effect) if price_effect is not None else None,
            fx_effect=rounded_money(fx_effect) if fx_effect is not None else None,
            costs=rounded_money(money_sum(costs)), trading_and_interaction=rounded_money(residual) if residual is not None else None,
            opening_value=first, ending_value=last, status="missing" if missing else "available"))
    valid = [row for row in rows if row["result"] is not None]
    unvalued = [event for event in events if model == "executions" and not event.get("ticker") and normalize_transaction_type(event["kind"]) in SHARE_INCREASE_TYPES | SHARE_DECREASE_TYPES and abs(event.get("shares") or 0) > 1e-9]
    complete = len(valid) == len(rows) and not unvalued
    cash_fx, other_cash, opening_cash_value, ending_cash_value, external_cash = 0.0, 0.0, None, None, 0.0
    if model == "executions":
        def cash_at(through):
            balances = defaultdict(float)
            for event in events:
                if event["date"] <= through:
                    balances[event["currency"]] += float(event.get("net") or 0)
            for flow in ledger["cash_flows"]:
                if flow["date"] <= through:
                    balances[flow["currency"]] += flow["amount"] * (-1 if flow["kind"] == "withdrawal" else 1)
            values = [amount * book.fx(currency, base, through) if book.fx(currency, base, through) is not None else None for currency, amount in balances.items() if abs(amount) > 1e-9]
            return None if any(value is None for value in values) else money_sum(values)
        opening_cash_value, ending_cash_value = cash_at(start), cash_at(end)
        movements = []
        for event in period:
            if not event.get("net"):
                continue
            fx = book.fx(event["currency"], base, event["date"])
            if fx is None:
                complete = False
                continue
            value = event["net"] * fx
            movements.append(value)
            kind = normalize_transaction_type(event["kind"])
            if kind in EXTERNAL:
                external_cash += value
            elif not event.get("ticker"):
                other_cash += value
        for flow in ledger["cash_flows"]:
            if start < flow["date"] <= end:
                fx = book.fx(flow["currency"], base, flow["date"])
                if fx is None:
                    complete = False
                    continue
                value = flow["amount"] * (-1 if flow["kind"] == "withdrawal" else 1) * fx
                movements.append(value)
                external_cash += value
        cash_fx = ending_cash_value - opening_cash_value - money_sum(movements) if opening_cash_value is not None and ending_cash_value is not None else None
        complete = complete and cash_fx is not None
    positions_result = money_sum(row["result"] for row in valid)
    return dict(model=model, start=start.isoformat(), end=end.isoformat(), currency=base, rows=rows,
        result=rounded_money(positions_result + (cash_fx or 0) + other_cash) if complete else None,
        positions_result=rounded_money(positions_result) if len(valid) == len(rows) else None,
        cash_fx=rounded_money(cash_fx) if cash_fx is not None else None,
        other_cash_result=rounded_money(other_cash), external_cash_flow=rounded_money(external_cash),
        opening_cash_value=opening_cash_value, ending_cash_value=ending_cash_value,
        covered_count=len(valid), total_count=len(rows) + len(unvalued), mismatched_tickers=mismatches,
        note="Positionsbeiträge aus gespeicherten Ausführungszyklen; Cash-Wechselkurseffekte separat. Kein TWR-Prozentbeitrag." if model == "executions" else "Simulation des heutigen Bestands. Keine historische Depotperformance: Ausführungen fehlen oder Bestände stimmen nicht überein.",
        decomposition="Kurs- und FX-Effekt beziehen sich auf den Anfangsbestand. Transaktionen und Wechselwirkungen sind separat ausgewiesen.")


_analysis_cache = OrderedDict()
_analysis_lock = RLock()


def invalidate_analysis_cache():
    with _analysis_lock:
        _analysis_cache.clear()


def get_analysis(*, sessions=21, sector_shock=-10.0, fx_shock=-5.0, shocked_sector="all"):
    key = (sessions, sector_shock, fx_shock, shocked_sector)
    # Coalesce simultaneous requests and avoid reloading the same stored history.
    # Portfolio writes clear this cache; successful read results live at most 30s.
    with _analysis_lock:
        cached = _analysis_cache.get(key)
        if cached and monotonic() - cached[0] < 30:
            return cached[1]
        result = _compute_analysis(sessions=sessions, sector_shock=sector_shock, fx_shock=fx_shock, shocked_sector=shocked_sector)
        _analysis_cache[key] = (monotonic(), result)
        _analysis_cache.move_to_end(key)
        while len(_analysis_cache) > 8:
            _analysis_cache.popitem(last=False)
        return result


def _compute_analysis(*, sessions=21, sector_shock=-10.0, fx_shock=-5.0, shocked_sector="all"):
    snapshot = get_portfolio_snapshot()
    positions = snapshot.positions
    base = snapshot.currency
    end = completed_us_market_session().date
    ledger = repository.ledger()
    tickers = sorted({position.ticker for position in positions} | {event["ticker"] for event in ledger["events"] if event.get("ticker")} | {"SPY"})
    currencies = {ticker: yahoo_quote_currency(ticker) for ticker in tickers}
    cash_balances = portfolio_repository.get_cash_balances()
    fx_currencies = {"GBP" if currency in {"GBp", "GBX"} else currency.upper() for currency in {base, *currencies.values(), *cash_balances.keys(), *[event["currency"] for event in ledger["events"]], *[flow["currency"] for flow in ledger["cash_flows"]]}}
    wanted = list(dict.fromkeys([*tickers, *[f"{currency}USD=X" for currency in fx_currencies if currency != "USD"]]))
    histories = prices.list_price_bars_for_tickers(wanted, start_date=end - timedelta(days=400))
    book = PriceBook(histories, currencies)
    days = [day for day, _ in book.points.get("SPY", []) if day <= end]
    start = days[-min(sessions + 1, len(days))] if days else end - timedelta(days=sessions * 2)
    result = attribution(ledger, book, start=start, end=end, base=base, positions=positions)
    notes = []
    try:
        members = list_group_members(TAXONOMY_VERSION, tickers=[position.ticker for position in positions])
    except Exception:
        members = []
        notes.append("Branchenzuordnungen derzeit nicht verfügbar.")
    context = {member.ticker: member for member in members}
    sectors, groups = defaultdict(float), defaultdict(float)
    for position in positions:
        member = context.get(position.ticker)
        sectors[member.sector if member else "Nicht zugeordnet"] += position.weight_pct
        groups[member.group_name if member else "Nicht zugeordnet"] += position.weight_pct
    portfolio_tickers = [position.ticker for position in positions]
    try:
        events = earnings.upcoming_earnings_events(portfolio_tickers, start_date=date.today(), end_date=date.today() + timedelta(days=30))
    except earnings.EarningsRepositoryUnavailable:
        events = []
        notes.append("Earningsdaten derzeit nicht verfügbar; Kalenderabdeckung unbekannt.")
    event_by_ticker = {event["ticker"]: event for event in events}
    event_rows = [{**event_by_ticker[position.ticker], "weight_pct": position.weight_pct} for position in positions if position.ticker in event_by_ticker]
    earnings_windows = [{"days": days_count, "weight_pct": round(sum(row["weight_pct"] for row in event_rows if date.fromisoformat(str(row["date"])) <= date.today() + timedelta(days=days_count)), 2)} for days_count in [7, 14, 30]]
    missing_weight = sum(position.weight_pct for position in positions if position.ticker not in event_by_ticker)
    frame = pd.DataFrame({position.ticker: {day: book.value(position.ticker, 1, day, base, exact=True) for day in days[-127:]} for position in positions})
    returns = frame.pct_change(fill_method=None)
    correlations = []
    for i, left in enumerate(portfolio_tickers):
        for right in portfolio_tickers[i + 1:]:
            common = returns[[left, right]].dropna()
            value = common[left].corr(common[right]) if len(common) >= 60 else None
            correlations.append(dict(left=left, right=right, observations=len(common), value=round(float(value), 3) if value is not None and isfinite(value) else None))
    affected = [position for position in positions if shocked_sector == "all" or (context.get(position.ticker) and context[position.ticker].sector == shocked_sector)]
    sector_impact = money_sum((position.base_market_value or 0) * sector_shock / 100 for position in affected)
    cash_fx_values = [amount * book.fx(currency, base, end) * fx_shock / 100 if book.fx(currency, base, end) is not None else None for currency, amount in cash_balances.items() if currency != base and amount]
    fx_impact = money_sum([*((position.base_market_value or 0) * fx_shock / 100 for position in positions if currencies[position.ticker] != base), *(value for value in cash_fx_values if value is not None)]) if all(value is not None for value in cash_fx_values) else None
    largest = sorted(positions, key=lambda position: position.weight_pct, reverse=True)
    stops = [dict(ticker=position.ticker, currency=position.currency, stop=position.stop_price,
                  distance_pct=(position.current_price - position.stop_price) / position.current_price * 100 if position.stop_price and position.current_price > 0 else None,
                  modeled_loss_pct=position.position_loss_risk_pct) for position in positions]
    return dict(as_of=end.isoformat(), currency=base, attribution=result,
        sectors=[dict(name=key, weight_pct=round(value, 2)) for key, value in sorted(sectors.items(), key=lambda item: -item[1])],
        industry_groups=[dict(name=key, weight_pct=round(value, 2)) for key, value in sorted(groups.items(), key=lambda item: -item[1])],
        top_positions=[dict(ticker=position.ticker, weight_pct=position.weight_pct) for position in largest[:5]],
        cash_ratio_pct=snapshot.cash_ratio_pct, stops=stops, correlations=correlations,
        correlation_note="Bis zu 126 gemeinsame Tagesrenditen in Basiswährung. Mindestens 60 vollständige Beobachtungen; keine Vorwärtsfüllung.",
        earnings=dict(windows=earnings_windows, missing_weight_pct=round(missing_weight, 2), rows=event_rows),
        scenarios=dict(sector=shocked_sector, sector_shock_pct=sector_shock, sector_impact=round(sector_impact, 2), fx_shock_pct=fx_shock, fx_impact=round(fx_impact, 2) if fx_impact is not None else None,
                       note="Unabhängige statische Szenarien auf aktuelle Bestände einschließlich Fremdwährungs-Cash. Kein Prognosemodell; keine Addition überlappender Schocks."),
        notes=notes + ["Gewichte beziehen sich auf das Gesamtdepot inklusive Cash.", "Fehlende Zuordnung wird nicht als Diversifikation gewertet.", "Stopprisiko ist eine Modellrechnung ohne garantierte Ausführung."])
