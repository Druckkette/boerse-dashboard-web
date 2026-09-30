from datetime import UTC, date, datetime

from app.services.trade_journal_backfill import _store_context


class _Result:
    def __init__(self, inserted_id: str | None) -> None:
        self.inserted_id = inserted_id

    def scalar_one_or_none(self) -> str | None:
        return self.inserted_id


class _Database:
    def __init__(self, inserted_id: str | None) -> None:
        self.inserted_id = inserted_id
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _Result(self.inserted_id)


def _context() -> dict:
    return {
        "status": "partial",
        "origin": "reconstruction_current_rules",
        "information_cutoff": datetime(2026, 9, 29, 23, 59, tzinfo=UTC),
        "data_as_of": date(2026, 9, 29),
        "archive_reference_id": None,
        "assessment_version": "journal_reconstruction_v1_current_rules",
        "ruleset_hash": "rules",
        "sources": ["price_bars"],
        "reason_codes": ["fundamentals_missing"],
        "payload": {
            "generated_at": "2026-09-30T05:00:00+00:00",
            "ticker": "NVDA",
        },
    }


def test_store_context_reports_insert_from_returning_id() -> None:
    db = _Database("version-id")

    assert _store_context(db, "entry-id", "stock", _context()) is True
    assert db.statement is not None


def test_store_context_reports_conflict_as_unchanged() -> None:
    db = _Database(None)

    assert _store_context(db, "entry-id", "stock", _context()) is False
