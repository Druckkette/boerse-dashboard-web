"""Atomic TR ledger ingestion and journal projection; only owned broker data is changed."""
from collections import defaultdict
from datetime import UTC, datetime
import hashlib

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ImportBatch, IsinMapping, Position, Transaction, TradeJournalEntry
from app.db.session import SessionLocal
from app.domain.portfolio.trade_ledger import allocate_trades
from app.domain.portfolio.trade_republic import TradeRepublicTransactionRow, reconstruct_open_positions


def transaction_row(row):
    raw = row.raw_json or {}
    timestamp = pd.Timestamp(raw.get("event_ts") or raw.get("datetime") or row.date)
    return TradeRepublicTransactionRow(date=pd.Timestamp(row.date), event_ts=timestamp,
        transaction_type=row.transaction_type, asset_class=raw.get("asset_class", "STOCK"),
        name=raw.get("name", row.ticker), isin=raw.get("isin") or raw.get("symbol", ""),
        shares=row.shares, price=row.price or 0, currency=row.currency, amount=row.gross_amount or 0,
        fee=row.fees or 0, tax=row.tax or 0, external_id=row.external_id, raw=raw)


def fingerprint(row):
    values = [str(row.event_ts), row.transaction_type.lower(), row.asset_class.upper(), row.isin.upper(),
              row.currency.upper(), *[format(float(v or 0), '.12g') for v in (row.shares, row.price, row.amount, row.fee, row.tax)]]
    return hashlib.sha256("|".join(values).encode()).hexdigest()


def merged_rows(incoming):
    with SessionLocal() as db:
        stored = list(db.scalars(select(Transaction).where(Transaction.broker == "Trade Republic").order_by(Transaction.created_at, Transaction.id)))
    rows = {row.id: transaction_row(row) for row in stored}
    matches = match_executions(incoming, stored)
    for index, item in enumerate(incoming):
        rows[matches.get(index) or f"new:{index}"] = item
    # Duplicated explicit broker IDs inside a report are the same execution.
    return sorted({row.external_id: row for row in rows.values()}.values(), key=lambda row: row.event_ts)


def match_executions(incoming, stored):
    ids = {row.external_id: row.id for row in stored}
    anonymous = defaultdict(list)
    for row in stored:
        if not (row.raw_json or {}).get("transaction_id"):
            anonymous[fingerprint(transaction_row(row))].append(row.id)
    seen = defaultdict(int)
    matches = {}
    for index, row in enumerate(incoming):
        broker_id = row.raw.get("transaction_id")
        if broker_id and row.external_id in ids:
            matches[index] = ids[row.external_id]
        elif not broker_id:
            key = fingerprint(row)
            occurrence = seen[key]
            seen[key] += 1
            if occurrence < len(anonymous[key]):
                matches[index] = anonymous[key][occurrence]
    return matches


def import_transactions(*, transactions, positions, mappings, file_name, replace_open_positions):
    from app.repositories.portfolio import PortfolioRepositoryUnavailable, TradeRepublicImportResult, _get_or_create_instrument
    try:
        with SessionLocal() as db:
            # Report imports for this one broker/account are serialized, including ledger replay.
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext('trade_republic_import'))"))
            batch = ImportBatch(source="trade_republic_transactions", file_name=file_name,
                status="running", rows_total=len(transactions), rows_imported=0, metadata_json={})
            db.add(batch)
            db.flush()
            stored = list(db.scalars(select(Transaction).where(Transaction.broker == "Trade Republic").order_by(Transaction.created_at, Transaction.id)))
            prior_rows = sorted((transaction_row(row) for row in stored), key=lambda row: row.event_ts)
            prior_mappings = {transaction_row(row).isin: row.ticker for row in stored if row.ticker}
            prior_positions, _ = reconstruct_open_positions(prior_rows, prior_mappings)
            matches = match_executions(transactions, stored)
            existing = {row.id: row for row in stored}
            by_external = {row.external_id: row for row in stored}
            for isin, ticker in mappings.items():
                instrument = _get_or_create_instrument(db, ticker=ticker, name=ticker, currency="EUR")
                mapping = db.scalar(select(IsinMapping).where(IsinMapping.isin == isin, IsinMapping.source == "trade_republic"))
                if mapping is None:
                    db.add(IsinMapping(isin=isin, ticker=ticker, instrument_id=instrument.id, source="trade_republic", confidence=1, metadata_json={}))
                elif mapping.ticker != ticker:
                    mapping.ticker, mapping.instrument_id = ticker, instrument.id
            inserted = 0
            for index, row in enumerate(transactions):
                target = existing.get(matches.get(index))
                if target is None and row.raw.get("transaction_id"):
                    target = by_external.get(row.external_id)
                if target is not None:
                    # Execution facts already imported remain immutable; only fill an absent ticker mapping.
                    if not target.ticker and mappings.get(row.isin):
                        target.ticker = mappings[row.isin]
                    continue
                ticker = mappings.get(row.isin, "")
                instrument = _get_or_create_instrument(db, ticker=ticker, name=row.name or ticker, currency=row.currency) if ticker else None
                target = Transaction(instrument_id=instrument.id if instrument else None, ticker=ticker,
                    date=row.date.date(), transaction_type=row.transaction_type.lower(), shares=abs(row.shares),
                    price=row.price or None, fees=row.fee, tax=row.tax, gross_amount=row.amount,
                    net_amount=row.cash_delta, currency=row.currency, broker="Trade Republic", external_id=row.external_id,
                    import_id=batch.id, raw_json={**row.raw, "source": "trade_republic_transactions", "isin": row.isin,
                        "event_ts": row.event_ts.isoformat(), "import_order": index, "cash_delta": row.cash_delta})
                db.add(target)
                db.flush()
                stored.append(target)
                by_external[row.external_id] = target
                inserted += 1
            # Rebuild from the stored union, not just the latest (possibly partial) CSV.
            stored.sort(key=lambda row: (transaction_row(row).event_ts, row.raw_json.get("import_order", 0), row.created_at, row.id))
            full_rows = [transaction_row(row) for row in stored]
            full_mappings = {row.raw_json.get("isin"): row.ticker for row in stored if row.ticker}
            full_mappings.update(mappings)
            current_positions, _ = reconstruct_open_positions(full_rows, full_mappings)
            events = allocate_trades([{
                "id": row.id, "timestamp": transaction_row(row).event_ts.isoformat(), "order": i,
                "date": row.date.isoformat(), "type": row.transaction_type, "ticker": row.ticker,
                "isin": transaction_row(row).isin, "asset_class": transaction_row(row).asset_class,
                "currency": row.currency, "shares": row.shares, "price": row.price,
                "fees": row.fees, "tax": row.tax,
            } for i, row in enumerate(stored)])
            journal_count = sync_journal(db, stored, events, current_positions, prior_positions)
            batch.status, batch.finished_at = "done", datetime.now(UTC)
            batch.rows_imported = len(current_positions)
            batch.metadata_json = {"journal_entries": journal_count, "transactions_inserted": inserted,
                "position_policy": "stored union; only matched Trade Republic cycles"}
            db.commit()
            return TradeRepublicImportResult(import_id=batch.id, rows_imported=len(current_positions),
                                             transactions_imported=inserted)
    except SQLAlchemyError as exc:
        raise PortfolioRepositoryUnavailable(str(exc)) from exc


def sync_journal(db, transactions, events, current_positions, prior_positions=()):
    from app.services.historical_sell import assess_historical_sale
    by_id = {row.id: row for row in transactions}
    groups = defaultdict(list)
    for event in events:
        groups[event["group"]].append(event)
    existing_entries = {row.source_transaction_id: row for row in db.scalars(
        select(TradeJournalEntry).where(TradeJournalEntry.source_transaction_id.in_([e["id"] for e in events])))}
    count = 0
    projected = set()
    for group_id, group in groups.items():
        buys = [e for e in group if e["type"] == "buy"]
        first, last = group[0], group[-1]
        position = db.scalar(select(Position).where(Position.import_trade_key == group_id))
        if position is None:
            # An older report can prepend a buy and change the cycle's first ID.
            linked_ids = {existing_entries[e["id"]].position_id for e in group
                          if e["id"] in existing_entries and existing_entries[e["id"]].position_id}
            if len(linked_ids) == 1:
                candidate = db.get(Position, next(iter(linked_ids)))
                if candidate and candidate.broker == "Trade Republic":
                    position = candidate
        if position is None and buys:
            candidates = list(db.scalars(select(Position).where(Position.ticker == first["ticker"],
                Position.broker == "Trade Republic", Position.buy_date == datetime.fromisoformat(buys[0]["date"]).date(),
                Position.import_trade_key.is_(None))))
            if len(candidates) == 1:
                position = candidates[0]
        if position is None and buys:
            position = Position(ticker=first["ticker"], instrument_id=by_id[first["id"]].instrument_id,
                shares=0, buy_price=buys[0]["price"] or 0, buy_date=datetime.fromisoformat(buys[0]["date"]).date(),
                currency=first["currency"], broker="Trade Republic", account="Trade Republic",
                note="Aus gespeicherten TR-Ausführungen rekonstruiert")
            db.add(position)
        if position is not None:
            position.import_trade_key = group_id
            # Current reconstructed holdings already account for splits and transfer events.
            current = next((p for p in current_positions if p.isin == first["isin"] and buys and p.first_buy_date == buys[0]["date"]), None)
            if current:
                projected.add((current.isin, current.first_buy_date))
            remaining = current.shares if current else last["remaining"]
            position.shares = remaining
            position.is_open = remaining > 1e-9
            position.closed_at = None if position.is_open else datetime.fromisoformat(last["date"]).replace(tzinfo=UTC)
            if current and position.currency == current.currency:
                position.buy_price = current.avg_buy_price
            elif current:
                # Legacy imports stored USD-converted entries. Preserve their recorded
                # conversion basis and stop denomination while updating weighted cost.
                prior = next((p for p in prior_positions if p.isin == current.isin), None)
                if prior and prior.avg_buy_price > 0:
                    stored_conversion = position.buy_price / prior.avg_buy_price
                    position.buy_price = current.avg_buy_price * stored_conversion
            db.flush()
        root_entry = None
        for event in group:
            entry = existing_entries.get(event["id"])
            if entry is None:
                # Only adopt a unique, exact execution match. Never infer a manual link by ticker alone.
                candidates = list(db.scalars(select(TradeJournalEntry).where(
                    TradeJournalEntry.source_transaction_id.is_(None), TradeJournalEntry.ticker == event["ticker"],
                    TradeJournalEntry.entry_type == event["type"], TradeJournalEntry.trade_date == datetime.fromisoformat(event["date"]).date(),
                    TradeJournalEntry.price == event["price"], TradeJournalEntry.shares == event["shares"],
                    TradeJournalEntry.currency == event["currency"])))
                entry = candidates[0] if len(candidates) == 1 else TradeJournalEntry(
                    ticker=event["ticker"], entry_type=event["type"], trade_date=datetime.fromisoformat(event["date"]).date(),
                    price=event["price"], shares=event["shares"], currency=event["currency"],
                    basis_text="Automatisch aus Trade-Republic-Ausführung übernommen.",
                    questionnaire_json={}, stock_snapshot_json={}, market_snapshot_json={}, chart_images_json={})
                db.add(entry)
                count += 1
            entry.source_transaction_id, entry.trade_group_id = event["id"], group_id
            entry.position_id = position.id if position else None
            by_id[event["id"]].position_id = entry.position_id
            if event["type"] == "buy":
                remaining = event["shares"] - sum(a["shares"] for sale in group for a in sale["allocations"] if a["buy_transaction_id"] == event["id"])
                entry.status = "closed" if remaining <= 1e-9 else "open"
                allocated = [a for sale in group for a in sale["allocations"] if a["buy_transaction_id"] == event["id"]]
                if allocated and all(a["pnl"] is not None for a in allocated):
                    entry.realized_pnl = sum(a["pnl"] for a in allocated)
                    cost = sum(a["cost_basis"] for a in allocated)
                    entry.realized_pnl_pct = entry.realized_pnl / cost * 100 if cost else None
                    entry.realized_pnl_eur = entry.realized_pnl if event["currency"] == "EUR" else None
            else:
                entry.status = "draft" if event["unallocated"] > 1e-9 else "closed"
                entry.realized_pnl, entry.realized_pnl_pct = event["pnl"], event["pnl_pct"]
                entry.realized_pnl_eur = event["pnl"] if event["currency"] == "EUR" else None
                if root_entry:
                    entry.linked_entry_id = root_entry.id
            metadata = {"source": "trade_republic", "currency": event["currency"], "allocation_method": "FIFO",
                        "fees": event["fees"], "tax": event["tax"], "remaining_shares": remaining if event["type"] == "buy" else event["remaining"],
                        "unallocated_shares": event["unallocated"], "allocations": event["allocations"],
                        "source_transaction_id": event["id"], "trade_group_id": group_id}
            if event["type"] == "sell" and (any((entry.portfolio_snapshot_json or {}).get(k) != v for k, v in metadata.items()) or not entry.sell_assessment_json):
                try:
                    with db.begin_nested():
                        entry.sell_assessment_json = assess_historical_sale(db, event)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Historical assessment failed for %s", event["ticker"])
                    entry.sell_assessment_json = {"status": "missing", "message": "Bewertung konnte nicht erstellt werden; Ausführung wurde importiert."}
            # Keep manual notes, charts and original market/stock assessments untouched.
            entry.portfolio_snapshot_json = {**(entry.portfolio_snapshot_json or {}), **metadata}
            db.flush()
            existing_entries[event["id"]] = entry
            if root_entry is None and event["type"] == "buy":
                root_entry = entry
    # Transfer-only holdings have no fabricated buy journal entry, but remain positions.
    active_transfer_keys = set()
    for current in current_positions:
        if (current.isin, current.first_buy_date) in projected:
            continue
        key = "transfer:" + hashlib.sha256(f"{current.isin}:{current.first_buy_date}".encode()).hexdigest()[:48]
        active_transfer_keys.add(key)
        position = db.scalar(select(Position).where(Position.import_trade_key == key))
        if position is None:
            candidates = list(db.scalars(select(Position).where(Position.ticker == current.ticker,
                Position.broker == "Trade Republic", Position.import_trade_key.is_(None), Position.is_open.is_(True))))
            position = candidates[0] if len(candidates) == 1 else Position(ticker=current.ticker,
                currency=current.currency, broker="Trade Republic", account="Trade Republic")
            db.add(position)
        position.import_trade_key = key
        position.shares, position.is_open, position.closed_at = current.shares, True, None
        position.buy_date = datetime.fromisoformat(current.first_buy_date).date() if current.first_buy_date else None
        if position.currency == current.currency:
            position.buy_price = current.avg_buy_price
    for position in db.scalars(select(Position).where(Position.broker == "Trade Republic",
            Position.import_trade_key.startswith("transfer:"), Position.is_open.is_(True))):
        if position.import_trade_key not in active_transfer_keys:
            position.shares, position.is_open = 0, False
    return count
