"""Idempotently project already stored TR executions after schema migration."""
from sqlalchemy import select
from app.db.models import Transaction
from app.db.session import SessionLocal
from app.repositories.tr_import import import_transactions


def backfill():
    with SessionLocal() as db:
        exists = db.scalar(select(Transaction.id).where(Transaction.broker == "Trade Republic").limit(1))
    if not exists:
        return {"skipped": True, "reason": "Keine gespeicherten TR-Ausführungen"}
    result = import_transactions(transactions=[], positions=[], mappings={},
        file_name="stored-ledger-backfill", replace_open_positions=False)
    return {"import_id": result.import_id, "open_positions": result.rows_imported,
            "transactions_inserted": result.transactions_imported}


if __name__ == "__main__":
    import json
    print(json.dumps(backfill()))
