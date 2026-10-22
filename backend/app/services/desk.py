"""Private decision workflows using saved prices; no order execution or provider fetches."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from math import isfinite
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.domain.desk import (
    Plan,
    curve_statistics,
    import_rows,
    in_quiet_hours,
    merge_import,
    money_weighted_return,
    plan_numbers,
)
from app.repositories import desk as repository, earnings, prices, relative_strength
from app.services.fx import _latest_cached_fx_rate, yahoo_quote_currency
from app.services.market_calendar import completed_us_market_session


def state():
    return project(repository.transact())


def changed_state():
    from app.services.home import invalidate_home_dashboard_cache

    invalidate_home_dashboard_cache()
    return state()


def project(value):
    return {
        **value,
        "accounts": [
            {k: v for k, v in row.items() if k != "transactions"}
            | {"transaction_count": len(row.get("transactions", []))}
            for row in value["accounts"]
        ],
    }


def fx_quote(source, target):
    expected = completed_us_market_session().date
    if source == target:
        return dict(
            source=source,
            target=target,
            rate=1.0,
            as_of=expected.isoformat(),
            provider="Gleiche Währung",
        )
    rates, stamps = {}, []
    for currency in {source, target}:
        if currency == "USD":
            rates[currency] = 1.0
        else:
            rate = _latest_cached_fx_rate(f"{currency}USD=X", pair=f"{currency}/USD")
            if rate is None or rate.as_of != expected or not isfinite(rate.rate) or rate.rate <= 0:
                raise ValueError(
                    f"Aktueller beobachteter Wechselkurs für {currency} fehlt. Wechselkurse unter Daten & System aktualisieren."
                )
            rates[currency] = rate.rate
            stamps.append(rate.as_of)
    return dict(
        source=source,
        target=target,
        rate=1.0 if source == target else rates[source] / rates[target],
        as_of=min(stamps).isoformat() if stamps else expected.isoformat(),
        provider="Kursdatenbank" if stamps else "Gleiche Währung",
    )


def save(collection, payload, *, item_id=None, revision):
    item_id = item_id or uuid4().hex

    def update(value):
        existing = next((row for row in value[collection] if row["id"] == item_id), None)
        if (
            len(value[collection])
            >= {"watchlists": 30, "plans": 100, "alerts": 100, "events": 500, "accounts": 20}[
                collection
            ]
            and existing is None
        ):
            raise ValueError("Die maximale Anzahl für diesen Bereich wurde erreicht.")
        item = {
            **(existing or {}),
            **payload.model_dump(mode="json"),
            "id": item_id,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if collection == "accounts":
            if (
                existing
                and existing.get("transactions")
                and item["currency"] != existing["currency"]
            ):
                raise ValueError(
                    "Die Basiswährung eines gebuchten Depots kann nicht verändert werden."
                )
            item.setdefault("transactions", [])
        if collection == "alerts":
            item.pop("last_condition", None)
            item.pop("last_sent_at", None)
        value[collection] = (
            [item if row["id"] == item_id else row for row in value[collection]]
            if existing
            else [*value[collection], item]
        )

    repository.transact(update, revision=revision)
    return changed_state()


def remove(collection, item_id, *, revision):
    def update(value):
        if collection == "watchlists" and item_id == "default":
            raise ValueError("Die Standard-Watchlist kann geleert, aber nicht entfernt werden.")
        item = next((row for row in value[collection] if row["id"] == item_id), None)
        if item is None:
            raise ValueError("Eintrag nicht gefunden.")
        if collection == "accounts" and (
            item.get("transactions") or any(p["account_id"] == item_id for p in value["plans"])
        ):
            raise ValueError(
                "Ein Depot mit Buchungen oder Plänen bleibt zur Nachvollziehbarkeit erhalten."
            )
        value[collection] = [row for row in value[collection] if row["id"] != item_id]

    repository.transact(update, revision=revision)
    return changed_state()


def account(account_id, *, value=None):
    if account_id == "main":
        from app.services.portfolio import get_portfolio_snapshot

        result = get_portfolio_snapshot().model_dump(mode="json")
        # Adapt the existing portfolio contract to the workspace account contract.
        # Prices/risk remain in quote currency, market values are in account currency.
        return {
            **result,
            "id": "main",
            "name": "Bestehendes Depot",
            "cash": result.get("cash_balance"),
            "positions": [
                {**p, "market_value": p.get("base_market_value")}
                for p in result.get("positions", [])
            ],
            "data_status": "available"
            if result.get("data_quality_status") == "trusted"
            else "limited",
            "transactions": [],
        }
    value = value or repository.transact()
    row = next((row for row in value["accounts"] if row["id"] == account_id), None)
    if row is None:
        raise ValueError("Depot nicht gefunden.")
    stamp = completed_us_market_session().date
    holdings, cash = defaultdict(float), defaultdict(float)
    for tx in row.get("transactions", []):
        kind, currency = tx["type"], tx["currency"]
        if kind == "buy":
            holdings[tx["ticker"]] += tx["shares"]
            cash[currency] -= tx["shares"] * tx["price"] + tx["fees"] + tx["tax"]
        elif kind == "sell":
            holdings[tx["ticker"]] -= tx["shares"]
            cash[currency] += tx["shares"] * tx["price"] - tx["fees"] - tx["tax"]
        elif kind == "split":
            holdings[tx["ticker"]] = tx["shares"]
            cash[currency] -= tx["fees"] + tx["tax"]
        else:
            cash[currency] += (
                tx["amount"] * (-1 if kind in {"withdrawal", "fee"} else 1) - tx["fees"] - tx["tax"]
            )
    converted_cash = 0.0
    missing, positions = [], []
    for currency, amount in cash.items():
        if abs(amount) < 1e-7:
            continue
        try:
            converted_cash += amount * fx_quote(currency, row["currency"])["rate"]
        except ValueError:
            missing.append(f"FX:{currency}")
    invested = 0.0
    for ticker, shares in holdings.items():
        if shares < 1e-7:
            continue
        bars = [
            b
            for b in prices.list_price_bars(ticker, start_date=stamp - timedelta(days=14))
            if b.date <= stamp and b.close is not None and isfinite(b.close) and b.close > 0
        ]
        last = bars[-1] if bars else None
        currency = yahoo_quote_currency(ticker)
        worth = None
        try:
            if last is None or last.date < stamp:
                raise ValueError()
            worth = shares * last.close * fx_quote(currency, row["currency"])["rate"]
            invested += worth
        except ValueError:
            missing.append(ticker)
        positions.append(
            dict(
                ticker=ticker,
                shares=shares,
                currency=currency,
                current_price=last.close if last else None,
                price_as_of=last.date.isoformat() if last else None,
                market_value=worth,
            )
        )
    return {
        **{k: v for k, v in row.items() if k != "transactions"},
        "transactions": list(reversed(row.get("transactions", [])))[0:250],
        "currency": row["currency"],
        "cash": None if any(m.startswith("FX:") for m in missing) else round(converted_cash, 2),
        "total_value": None if missing else round(invested + converted_cash, 2),
        "positions": positions,
        "missing": missing,
        "as_of": stamp.isoformat(),
        "data_status": "limited" if missing else "available",
    }


def transfer_watchlist(payload, *, revision):
    def update(value):
        if payload.source == payload.target:
            raise ValueError("Eine andere Zielliste wählen.")
        source = next((row for row in value["watchlists"] if row["id"] == payload.source), None)
        target = next((row for row in value["watchlists"] if row["id"] == payload.target), None)
        if source is None or target is None:
            raise ValueError("Liste nicht gefunden.")
        selected = [item for item in source["items"] if item["ticker"] in payload.tickers]
        if len(selected) != len(set(payload.tickers)):
            raise ValueError("Die Auswahl hat sich geändert. Liste neu laden.")
        existing = {item["ticker"]: item for item in target["items"]}
        if payload.move and any(
            existing[item["ticker"]] != item for item in selected if item["ticker"] in existing
        ):
            raise ValueError(
                "Im Ziel bestehen abweichende Notizen. Zuerst kopieren oder die Einträge abgleichen."
            )
        target["items"] += [item for item in selected if item["ticker"] not in existing]
        if len(target["items"]) > 100:
            raise ValueError("Eine Watchlist darf höchstens 100 Aktien enthalten.")
        if payload.move:
            source["items"] = [
                item for item in source["items"] if item["ticker"] not in payload.tickers
            ]

    repository.transact(update, revision=revision)
    return changed_state()


def import_account(account_id, payload, *, revision):
    if account_id == "main":
        raise ValueError("Für das bestehende Depot bitte den vorhandenen TR-Import verwenden.")
    incoming = import_rows(payload.csv)
    preview = {}

    def apply(value):
        row = next((row for row in value["accounts"] if row["id"] == account_id), None)
        if row is None:
            raise ValueError("Depot nicht gefunden.")
        merged, duplicates = merge_import(row.get("transactions", []), incoming)
        digest = hashlib.sha256(
            json.dumps([account_id, merged], sort_keys=True).encode()
        ).hexdigest()
        preview.update(
            rows=incoming[:100],
            count=len(incoming),
            duplicates=duplicates,
            added=len(incoming) - duplicates,
            preview_hash=digest,
        )
        if payload.commit:
            if payload.preview_hash != digest:
                raise ValueError("Die Importvorschau hat sich geändert. Bitte erneut prüfen.")
            row["transactions"] = merged

    if payload.commit:
        repository.transact(apply, revision=revision)
    else:
        current = repository.transact()
        if current["revision"] != revision:
            raise repository.DeskConflict("Daten wurden geändert. Neu laden.")
        apply(current)
    return {
        **preview,
        "committed": payload.commit,
        "state": changed_state() if payload.commit else state(),
    }


def capture(ticker):
    from app.services.stocks import get_stock_assessment

    result = get_stock_assessment(ticker).model_dump(mode="json")
    return {
        key: result.get(key)
        for key in (
            "as_of",
            "calculation",
            "data_quality",
            "scores",
            "metrics",
            "checks",
            "verdict_label",
            "message",
            "overall_v2",
            "technical_v2",
            "fundamental_v2",
            "chart_v2",
            "moving_average_v2",
            "setup",
            "eligibility",
            "chart_signals",
            "drivers",
            "warnings",
        )
    }


def preview_plan(payload: Plan):
    depot = account(payload.account_id)
    if depot.get("total_value") is None or depot.get("cash") is None:
        raise ValueError(
            "Das Depot ist wegen fehlender Kurse oder Wechselkurse nicht vollständig bewertbar."
        )
    from app.services.market_calendar import completed_ticker_market_session

    if any(
        not p.get("price_as_of")
        or date.fromisoformat(str(p["price_as_of"])[:10])
        < completed_ticker_market_session(p["ticker"]).date
        for p in depot.get("positions", [])
    ):
        raise ValueError("Für die Einstiegsplanung fehlen aktuelle abgeschlossene Kurse im Depot.")
    rate = fx_quote(payload.currency, depot["currency"])
    positions = depot.get("positions", [])
    existing_risk = (
        sum(
            p["position_loss_risk"] * fx_quote(p["currency"], depot["currency"])["rate"]
            for p in positions
        )
        if all(p.get("position_loss_risk") is not None for p in positions)
        else None
    )
    basis = {
        "currency": depot["currency"],
        "total_value": depot["total_value"],
        "cash": depot["cash"],
        "positions": sorted(
            [
                {
                    key: p.get(key)
                    for key in (
                        "ticker",
                        "shares",
                        "market_value",
                        "price_as_of",
                        "currency",
                        "position_loss_risk",
                    )
                }
                for p in positions
            ],
            key=lambda p: p["ticker"],
        ),
    }
    result = {
        **plan_numbers(
            payload,
            total=depot["total_value"],
            cash=depot["cash"],
            fx=rate["rate"],
            existing_risk=existing_risk,
        ),
        "account_currency": depot["currency"],
        "quote_currency": payload.currency,
        "fx_as_of": rate["as_of"],
        "account_basis": basis,
        "assessment": capture(payload.ticker),
    }
    result["preview_hash"] = hashlib.sha256(
        json.dumps([payload.model_dump(mode="json"), result], sort_keys=True).encode()
    ).hexdigest()
    return result


def create_plan(payload, *, revision, preview_hash):
    preview = preview_plan(payload)
    if preview["preview_hash"] != preview_hash:
        raise repository.DeskConflict(
            "Bewertung, Cash oder Wechselkurs haben sich geändert. Plan erneut berechnen."
        )
    if preview["shares"] < 1:
        raise ValueError("Das verfügbare Cash oder Risikobudget reicht für keine ganze Aktie.")

    def update(value):
        if len(value["plans"]) >= 100:
            raise ValueError("Maximal 100 dokumentierte Pläne.")
        now = datetime.now(UTC).isoformat()
        value["plans"].insert(
            0,
            {
                **payload.model_dump(mode="json"),
                "id": uuid4().hex,
                "stage": "planned",
                "created_at": now,
                "preview": preview,
                "history": [dict(at=now, stage="planned", note=payload.thesis, preview=preview)],
            },
        )
        for watchlist in value["watchlists"]:
            for item in watchlist["items"]:
                if item["ticker"] == payload.ticker:
                    item["stage"] = "planned"

    repository.transact(update, revision=revision)
    return changed_state()


def stage_plan(plan_id, payload, *, revision):
    def update(value):
        plan = next((row for row in value["plans"] if row["id"] == plan_id), None)
        if plan is None:
            raise ValueError("Plan nicht gefunden.")
        if len(plan["history"]) >= 100:
            raise ValueError("Maximal 100 dokumentierte Prüfschritte je Plan.")
        plan["history"].append(
            dict(at=datetime.now(UTC).isoformat(), stage=payload.stage, note=payload.note)
        )
        plan["stage"] = payload.stage
        for watchlist in value["watchlists"]:
            for item in watchlist["items"]:
                if item["ticker"] == plan["ticker"] and payload.stage != "archived":
                    item["stage"] = payload.stage

    repository.transact(update, revision=revision)
    return changed_state()


def calendar(*, days=35, scope="all"):
    from app.repositories import portfolio

    value = repository.transact()
    notes = []
    try:
        portfolio_tickers = {p.ticker for p in portfolio.list_open_positions()}
    except portfolio.PortfolioRepositoryUnavailable:
        portfolio_tickers = set()
        notes.append("Bestehendes Depot konnte für die Terminauswahl nicht einbezogen werden.")
    # Calendar membership needs quantities, not quotes or FX valuations.
    for row in value["accounts"]:
        holdings = defaultdict(float)
        for tx in row.get("transactions", []):
            if tx["type"] == "split":
                holdings[tx["ticker"]] = tx["shares"]
            elif tx["type"] in {"buy", "sell"}:
                holdings[tx["ticker"]] += tx["shares"] * (-1 if tx["type"] == "sell" else 1)
        portfolio_tickers.update(t for t, quantity in holdings.items() if quantity > 1e-7)
    watch_tickers = {item["ticker"] for row in value["watchlists"] for item in row["items"]}
    selected = (
        portfolio_tickers
        if scope == "portfolio"
        else watch_tickers
        if scope == "watchlist"
        else portfolio_tickers | watch_tickers
    )
    start = datetime.now(ZoneInfo("Europe/Berlin")).date()
    end = start + timedelta(days=days)
    try:
        provider_rows = earnings.upcoming_earnings_events(
            sorted(selected), start_date=start, end_date=end
        )
    except earnings.EarningsRepositoryUnavailable:
        provider_rows = []
        notes.append("Gespeicherte Anbietertermine konnten nicht geladen werden.")
    rows = [
        {
            **row,
            "id": f"earnings:{row['ticker']}:{row['date']}",
            "kind": "earnings",
            "title": f"{row['ticker']} · Quartalszahlen",
            "note": "Anbietertermin; Uhrzeit unbekannt" if not row.get("time") else "",
            "scope": "portfolio" if row["ticker"] in portfolio_tickers else "watchlist",
        }
        for row in provider_rows
    ]
    rows += [
        {
            **row,
            "source": "Eigener Termin",
            "scope": "portfolio"
            if row["ticker"] in portfolio_tickers
            else "watchlist"
            if row["ticker"] in watch_tickers
            else "personal",
        }
        for row in value["events"]
        if start.isoformat() <= row["date"] <= end.isoformat()
        and (scope == "all" or row["ticker"] in selected)
    ]
    return dict(
        as_of=start.isoformat(),
        rows=sorted(rows, key=lambda row: (row["date"], row["title"])),
        coverage_note=" ".join(notes),
    )


def observe(rule):
    expected = completed_us_market_session().date
    if rule["kind"] == "earnings":
        dates = earnings.next_earnings_dates([rule["ticker"]])
        stamp = dates.get(rule["ticker"])
        return (
            stamp is not None and 0 <= (stamp - date.today()).days <= rule["threshold"],
            f"Nächste Quartalszahlen: {stamp or 'Termin fehlt'}",
            expected.isoformat(),
        )
    if rule["kind"] == "data":
        from app.services.data_quality import build_data_diagnostics

        result = build_data_diagnostics()
        result = result.model_dump() if hasattr(result, "model_dump") else result
        return (
            result.get("decision_status") != "trusted",
            result.get("summary", "Datenstatus prüfen"),
            expected.isoformat(),
        )
    if rule["kind"] == "rs_below":
        from app.services.relative_strength import configured_rs_source

        row = relative_strength.get_latest_rs_rating(rule["ticker"], source=configured_rs_source())
        if row is None or row.date != expected or row.rating is None:
            raise ValueError("Aktuelles RS-Rating fehlt.")
        return (
            row.rating < rule["threshold"],
            f"RS {row.rating} unter Schwelle {rule['threshold']:g}",
            row.date.isoformat(),
        )
    rows = [
        b
        for b in prices.list_price_bars(rule["ticker"], start_date=expected - timedelta(days=14))
        if b.date <= expected and b.close is not None and isfinite(b.close) and b.close > 0
    ]
    if not rows or rows[-1].date < expected:
        raise ValueError("Aktueller abgeschlossener Tageskurs fehlt.")
    price, threshold = rows[-1].close, rule["threshold"]
    if rule["kind"] == "stop":
        from app.services.portfolio import get_portfolio_positions

        positions = [
            p
            for p in get_portfolio_positions()
            if p.ticker == rule["ticker"] and p.stop_price is not None
        ]
        if not positions:
            raise ValueError("Kein gespeicherter Stopp im bestehenden Depot.")
        # Monitor and quote must be expressed in the same observed quote currency.
        position = positions[0]
        threshold = (
            position.stop_price
            * fx_quote(position.currency, yahoo_quote_currency(rule["ticker"]))["rate"]
        )
    triggered = price >= threshold if rule["kind"] == "price_above" else price <= threshold
    return (
        triggered,
        f"Schlusskurs {price:g} · Schwelle {threshold:g} {yahoo_quote_currency(rule['ticker'])}",
        rows[-1].date.isoformat(),
    )


def evaluate_alerts(*, now=None):
    now = now or datetime.now(UTC)
    current = repository.transact()
    observations = {}
    for rule in current["alerts"]:
        if rule["enabled"]:
            try:
                observations[rule["id"]] = observe(rule)
            except Exception as exc:
                observations[rule["id"]] = (None, str(exc)[:500], None)
    if not observations:
        return state()

    def update(value):
        for rule in value["alerts"]:
            if rule["id"] not in observations:
                continue
            triggered, detail, as_of = observations[rule["id"]]
            rule.update(
                checked_at=now.isoformat(),
                check_status="missing"
                if triggered is None
                else "triggered"
                if triggered
                else "clear",
                check_detail=detail,
            )
            if triggered is None:
                continue
            if not triggered:
                rule["active"] = False
                continue
            last = (
                datetime.fromisoformat(rule["last_sent_at"]) if rule.get("last_sent_at") else None
            )
            if (
                rule.get("active")
                and last
                and now - last < timedelta(minutes=rule["repeat_minutes"])
            ):
                continue
            if in_quiet_hours(
                now.astimezone(ZoneInfo("Europe/Berlin")), rule["quiet_start"], rule["quiet_end"]
            ):
                rule["check_status"] = "quiet"
                continue
            entry = dict(
                id=uuid4().hex,
                rule_id=rule["id"],
                name=rule["name"],
                ticker=rule["ticker"],
                kind=rule["kind"],
                detail=detail,
                as_of=as_of,
                at=now.isoformat(),
                acknowledged_at=None,
                push_status="pending" if rule["push"] else "off",
            )
            value["history"].insert(0, entry)
            rule.update(active=True, last_sent_at=now.isoformat())
        value["history"] = value["history"][:500]

    # Ignore stale observations if a user edited a rule while reads were in progress.
    repository.transact(update, revision=current["revision"])
    return changed_state()


def acknowledge(history_id, *, revision):
    def update(value):
        row = next((r for r in value["history"] if r["id"] == history_id), None)
        if row is None:
            raise ValueError("Meldung nicht gefunden.")
        row["acknowledged_at"] = datetime.now(UTC).isoformat()

    repository.transact(update, revision=revision)
    return changed_state()


def account_overview():
    value = repository.transact()
    rows, missing, total = [], [], 0.0
    for account_id in ["main", *[row["id"] for row in value["accounts"]]]:
        try:
            view = account(account_id, value=value)
            row = {
                key: view.get(key)
                for key in ("id", "name", "currency", "cash", "total_value", "data_status")
            }
            row["positions_count"] = len(view["positions"])
            if view["total_value"] is None:
                raise ValueError("Bewertung unvollständig")
            total += view["total_value"] * fx_quote(view["currency"], "EUR")["rate"]
            rows.append(row)
        except (ValueError, RuntimeError):
            missing.append(account_id)
            rows.append(
                dict(
                    id=account_id,
                    name="Bestehendes Depot"
                    if account_id == "main"
                    else next(r["name"] for r in value["accounts"] if r["id"] == account_id),
                    total_value=None,
                    cash=None,
                    currency="EUR",
                    data_status="missing",
                    positions_count=None,
                )
            )
    return dict(
        rows=rows, currency="EUR", total_value=None if missing else round(total, 2), missing=missing
    )


def historical_value(book, ticker, quantity, day, base):
    from app.services.market_calendar import common_market_sessions

    open_session = len(common_market_sessions(ticker, ticker, day, day)) > 0
    return book.value(ticker, quantity, day, base, exact=open_session)


def performance(*, start: date, benchmark: str, account_id="main"):
    if account_id != "main":
        return account_performance(account_id, start=start, benchmark=benchmark)
    from app.services.portfolio import get_portfolio_curve
    from app.repositories.analysis import ledger
    from app.services.portfolio_analysis import PriceBook
    from app.services.portfolio import TR_EXTERNAL_FLOW_TYPES

    curve = get_portfolio_curve(start_date=start, model="execution_history")
    points = [p.model_dump() for p in curve.points]
    statistics = curve_statistics(points, historical=curve.model == "execution_history")
    result = dict(
        **statistics,
        currency=curve.currency,
        start=points[0]["date"] if points else start.isoformat(),
        end=curve.as_of,
        benchmark=benchmark,
        benchmark_return_pct=None,
        mwr_annual_pct=None,
        period_result=None,
        external_flow=None,
        benchmark_note="Basis: importierte TR-Ausführungen. Benchmark: Kursrendite in Depotwährung, keine Gesamtrendite inklusive Ausschüttungen.",
        points=points,
    )
    if not points:
        return result
    begin, end = date.fromisoformat(points[0]["date"]), date.fromisoformat(points[-1]["date"])
    histories = {
        ticker: prices.list_price_bars(ticker, start_date=begin - timedelta(days=7))
        for ticker in {benchmark, f"{curve.currency}USD=X"}
    }
    book = PriceBook(histories, {benchmark: yahoo_quote_currency(benchmark)})
    first_benchmark = historical_value(book, benchmark, 1, begin, curve.currency)
    for point in points:
        benchmark_value = historical_value(
            book, benchmark, 1, date.fromisoformat(point["date"]), curve.currency
        )
        point["benchmark_index"] = (
            benchmark_value / first_benchmark * 100
            if benchmark_value is not None and first_benchmark
            else None
        )
    if points[0]["benchmark_index"] and points[-1]["benchmark_index"]:
        result["benchmark_return_pct"] = (
            points[-1]["benchmark_index"] / points[0]["benchmark_index"] - 1
        ) * 100
    if (
        not statistics["complete"]
        or curve.model != "execution_history"
        or points[0].get("depot_value") is None
        or points[-1].get("depot_value") is None
    ):
        return result
    source = ledger()
    external = []
    from app.domain.portfolio.trade_republic import normalize_transaction_type

    events = [
        dict(date=row["date"], amount=row["net"], currency=row["currency"])
        for row in source["events"]
        if row.get("raw", {}).get("source") == "trade_republic_transactions"
        and normalize_transaction_type(row["kind"]) in TR_EXTERNAL_FLOW_TYPES
    ]
    # Transfers of securities need market-valued external flows, not their often-zero cash amount.
    if any(
        row["kind"] in {"transfer_in", "transfer_out"} and begin < row["date"] <= end
        for row in source["events"]
    ):
        result["note"] += (
            " Geldgewichtete Rendite bei Wertpapierüberträgen derzeit nicht ausgewiesen."
        )
        return result
    currencies = {row["currency"] for row in events}
    fx_histories = {
        f"{currency}USD=X": prices.list_price_bars(
            f"{currency}USD=X", start_date=begin - timedelta(days=7)
        )
        for currency in currencies | {curve.currency}
        if currency != "USD"
    }
    fx_book = PriceBook(fx_histories, {})
    for row in events:
        if not begin < row["date"] <= end:
            continue
        rate = fx_book.fx(row["currency"], curve.currency, row["date"])
        if rate is None:
            return result
        external.append((row["date"], row["amount"] * rate))
    flow = sum(v for _, v in external)
    initial, terminal = points[0]["depot_value"], points[-1]["depot_value"]
    result.update(
        external_flow=round(flow, 2),
        period_result=round(terminal - initial - flow, 2),
        mwr_annual_pct=money_weighted_return(
            [(begin, -initial), *[(d, -v) for d, v in external], (end, terminal)]
        ),
    )
    return result


def account_performance(account_id, *, start, benchmark):
    """Historical NAV for an additional account, from its own execution ledger."""
    from app.services.market_calendar import common_market_sessions
    from app.services.portfolio_analysis import PriceBook

    value = repository.transact()
    row = next((r for r in value["accounts"] if r["id"] == account_id), None)
    if row is None:
        raise ValueError("Depot nicht gefunden.")
    end = completed_us_market_session().date
    transactions = [r for r in row.get("transactions", []) if date.fromisoformat(r["date"]) <= end]
    first_date = max(start, date.fromisoformat(transactions[0]["date"])) if transactions else start
    sessions = (
        common_market_sessions("SPY", benchmark, first_date, end)
        if first_date <= end and transactions
        else []
    )
    tickers = {r["ticker"] for r in transactions if r["type"] in {"buy", "sell", "split"}}
    currencies = (
        {r["currency"] for r in transactions}
        | {row["currency"], yahoo_quote_currency(benchmark)}
        | {yahoo_quote_currency(t) for t in tickers}
    )
    symbols = tickers | {benchmark} | {f"{c}USD=X" for c in currencies if c != "USD"}
    histories = (
        prices.list_price_bars_for_tickers(symbols, start_date=first_date - timedelta(days=10))
        if sessions is not None and len(sessions)
        else {}
    )
    currencies_by_ticker = {t: yahoo_quote_currency(t) for t in tickers | {benchmark}}
    benchmark_book = PriceBook(histories, currencies_by_ticker)
    # Yahoo Close is split-adjusted to the download date. Execution quantities
    # need the contemporaneous quote, while the passive benchmark stays adjusted.
    restored = dict(histories)
    booked_splits = [
        (tx["ticker"], date.fromisoformat(tx["date"]))
        for tx in transactions
        if tx["type"] == "split"
    ]
    for ticker in tickers:
        restored[ticker] = []
        for bar in histories.get(ticker, []):
            factor = getattr(bar, "split_adjustment_factor", None)
            close = bar.close
            if getattr(bar, "source", "yfinance") == "yfinance":
                if factor is not None:
                    close = (
                        close * factor
                        if close is not None and isfinite(factor) and factor > 0
                        else None
                    )
                elif any(t == ticker and bar.date < day <= end for t, day in booked_splits):
                    close = None  # Legacy split basis must be refreshed, never guessed.
            restored[ticker].append(SimpleNamespace(date=bar.date, close=close))
    book = PriceBook(restored, currencies_by_ticker)
    holdings, cash, points, external = defaultdict(float), defaultdict(float), [], []
    previous_nav = previous_index = None
    cursor = 0
    interrupted = False
    benchmark_start = None
    for session in sessions:
        day = session.date()
        daily_external = 0.0
        flow_missing = False
        while (
            cursor < len(transactions) and date.fromisoformat(transactions[cursor]["date"]) <= day
        ):
            tx = transactions[cursor]
            kind, currency = tx["type"], tx["currency"]
            cost = tx["fees"] + tx["tax"]
            if kind == "buy":
                holdings[tx["ticker"]] += tx["shares"]
                cash[currency] -= tx["shares"] * tx["price"] + cost
            elif kind == "sell":
                holdings[tx["ticker"]] -= tx["shares"]
                cash[currency] += tx["shares"] * tx["price"] - cost
            elif kind == "split":
                holdings[tx["ticker"]] = tx["shares"]
                cash[currency] -= cost
            else:
                amount = tx["amount"] * (-1 if kind in {"fee", "withdrawal"} else 1)
                cash[currency] += amount - cost
                if kind in {"deposit", "withdrawal"} and points:
                    stamp = date.fromisoformat(tx["date"])
                    rate = book.fx(currency, row["currency"], stamp)
                    if rate is None:
                        flow_missing = True
                    else:
                        daily_external += amount * rate
                        external.append((stamp, amount * rate))
            cursor += 1
        values = [
            historical_value(book, t, quantity, day, row["currency"])
            for t, quantity in holdings.items()
            if abs(quantity) > 1e-7
        ]
        for currency, amount in cash.items():
            if abs(amount) > 1e-7:
                rate = book.fx(currency, row["currency"], day, exact=True)
                values.append(amount * rate if rate is not None else None)
        nav = sum(values) if all(v is not None for v in values) and not flow_missing else None
        if nav is None:
            interrupted |= bool(daily_external) or flow_missing
            index = None
        elif previous_nav is None:
            index = 100.0 if nav > 0 and not points else None
        elif previous_nav > 0 and previous_index is not None and not interrupted:
            index = previous_index * (nav - daily_external) / previous_nav
        else:
            index = None
        benchmark_value = historical_value(benchmark_book, benchmark, 1, day, row["currency"])
        if not points:
            benchmark_start = benchmark_value
        points.append(
            dict(
                date=day.isoformat(),
                depot_value=nav,
                portfolio_index=index,
                benchmark_index=benchmark_value / benchmark_start * 100
                if benchmark_value is not None and benchmark_start
                else None,
            )
        )
        if nav is not None:
            previous_nav, previous_index = nav, index
    statistics = curve_statistics(points, historical=True)
    result = dict(
        **statistics,
        currency=row["currency"],
        start=points[0]["date"] if points else first_date.isoformat(),
        end=end.isoformat(),
        benchmark=benchmark,
        benchmark_return_pct=None,
        mwr_annual_pct=None,
        period_result=None,
        external_flow=None,
        benchmark_note="Basis: Buchungen dieses Depots und gespeicherte Splitfaktoren; fehlende Splitbasis erfordert einen Kursrefresh. Benchmark: Kursrendite in Depotwährung ohne Ausschüttungen; letzter beobachteter Kurs an Feiertagen, höchstens vier Kalendertage alt.",
        points=points,
    )
    if points and points[0]["benchmark_index"] and points[-1]["benchmark_index"]:
        result["benchmark_return_pct"] = (
            points[-1]["benchmark_index"] / points[0]["benchmark_index"] - 1
        ) * 100
    if statistics["complete"]:
        initial, terminal = points[0]["depot_value"], points[-1]["depot_value"]
        flows = sum(amount for _, amount in external)
        result.update(
            period_result=round(terminal - initial - flows, 2),
            external_flow=round(flows, 2),
            mwr_annual_pct=money_weighted_return(
                [
                    (date.fromisoformat(points[0]["date"]), -initial),
                    *[(day, -amount) for day, amount in external],
                    (date.fromisoformat(points[-1]["date"]), terminal),
                ]
            ),
        )
    return result
