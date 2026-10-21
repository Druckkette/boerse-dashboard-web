"""One transaction boundary for portfolio imports, corrections and bookings."""
from sqlalchemy import text


def lock_positions(db) -> None:
    # Imports may replace the whole portfolio. Serialize the short database writes
    # across every writer, including the independently replayed broker ledger.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('portfolio_positions'))"))
