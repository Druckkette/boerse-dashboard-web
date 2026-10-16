"""Idempotently project already stored TR executions after schema migration."""
from collections import Counter
from sqlalchemy import select, text
from app.db.models import Transaction, TradeJournalEntry
from app.db.session import SessionLocal
from app.repositories.tr_import import import_transactions, sync_journal, transaction_row
from app.domain.portfolio.trade_ledger import allocate_trades


def backfill_missing_symbols():
    """Add journal projections only; preserve every stored execution and position."""
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('trade_republic_import'))"))
        stored = list(db.scalars(select(Transaction).where(Transaction.broker == "Trade Republic")))
        stored.sort(key=lambda row: (transaction_row(row).event_ts, (row.raw_json or {}).get("import_order", 0), row.created_at, row.id))
        events = allocate_trades([{
            "id": row.id, "timestamp": transaction_row(row).event_ts.isoformat(), "order": index,
            "date": row.date.isoformat(), "type": row.transaction_type, "ticker": row.ticker,
            "isin": transaction_row(row).isin, "asset_class": transaction_row(row).asset_class,
            "currency": row.currency, "shares": row.shares, "price": row.price,
            "fees": row.fees, "tax": row.tax,
        } for index, row in enumerate(stored)])
        unresolved = [event for event in events if not event["symbol_resolved"]]
        groups = {event["group"] for event in unresolved}
        # Keep complete cycles, including any previously mapped sibling executions.
        count = sync_journal(db, stored, [event for event in events if event["group"] in groups], [], journal_only=True)
        db.commit()
        return {"journal_entries_added": count, "unmapped_executions": len(unresolved),
                "transactions_inserted": 0, "positions_changed": 0}


def backfill():
    with SessionLocal() as db:
        exists = db.scalar(select(Transaction.id).where(Transaction.broker == "Trade Republic").limit(1))
    if not exists:
        return {"skipped": True, "reason": "Keine gespeicherten TR-Ausführungen"}
    result = import_transactions(transactions=[], positions=[], mappings={},
        file_name="stored-ledger-backfill", replace_open_positions=False)
    with SessionLocal() as db:
        assessments = list(db.scalars(select(TradeJournalEntry.sell_assessment_json).where(
            TradeJournalEntry.source_transaction_id.is_not(None), TradeJournalEntry.entry_type == "sell")))
    counts = Counter(item.get("status", "missing") for item in assessments)
    reasons = Counter(item.get("reason_code") or item.get("message", "Unbekannt")
                      for item in assessments if item.get("status") != "available")
    return {"assessments": dict(counts), "missing_reasons": dict(reasons), "import_id": result.import_id, "open_positions": result.rows_imported,
            "transactions_inserted": result.transactions_imported}


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing-symbols-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(backfill_missing_symbols() if args.missing_symbols_only else backfill()))
