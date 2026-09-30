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


def test_stock_reconstruction_computes_partial_scores_without_future_fundamentals(monkeypatch):
    from datetime import timedelta
    from app.db.models import Instrument, PriceBar, TradeJournalEntry
    from app.services import trade_journal_backfill as service

    day = date(2026, 9, 21)
    bars = [PriceBar(date=day - timedelta(days=259-i), open=100+i/10,
                     high=101+i/10, low=99+i/10, close=100+i/10,
                     volume=100000+i*100, source="test") for i in range(260)]

    class Rows:
        def __init__(self, items):
            self.items = items
        def all(self):
            return self.items

    class Database:
        def __init__(self):
            self.values = iter([None, Instrument(id="instrument", ticker="TEST", currency="EUR"), None, None])
            self.rows = iter([bars[::-1], []])
            self.statements = []
        def scalar(self, statement):
            self.statements.append(str(statement))
            return next(self.values)
        def scalars(self, statement):
            self.statements.append(str(statement))
            return Rows(next(self.rows))

    monkeypatch.setattr(service, "_bars_for_ticker", lambda *args: bars)
    monkeypatch.setattr(service, "_assessment_score_weights", lambda: {})
    db = Database()
    context = service._stock_context(db, TradeJournalEntry(ticker="TEST"), day,
                                     datetime(2026, 9, 21, 23, 59, tzinfo=UTC))
    assessment = context["payload"]["assessment"]
    assert 0 <= assessment["technical_v2"]["score"] <= 100
    assert 0 <= assessment["chart_v2"]["score"] <= 100
    assert assessment["fundamental_v2"]["score"] is None
    assert assessment["overall_v2"]["score"] is None
    assert context["payload"]["metrics"]["last_close"] == bars[-1].close
    assert context["payload"]["quote_currency"] == "USD"
    assert context["status"] == "partial"
    assert "fundamentals_missing" in context["reason_codes"]
    assert any("fundamental_snapshots.updated_at <=" in sql for sql in db.statements)
    assert any("price_bars.date <=" in sql for sql in db.statements)


def test_context_fingerprint_ignores_generation_time_but_not_score_changes():
    from copy import deepcopy
    from app.services.trade_journal_backfill import _store_context
    first, second = _context(), deepcopy(_context())
    second["payload"]["generated_at"] = "2026-10-01T05:00:00+00:00"
    db1, db2 = _Database(None), _Database(None)
    _store_context(db1, "entry", "stock", first)
    _store_context(db2, "entry", "stock", second)
    fp1 = db1.statement.compile().params["data_fingerprint"]
    assert db2.statement.compile().params["data_fingerprint"] == fp1
    second["payload"]["assessment"] = {"technical_v2": {"score": 80}}
    _store_context(db2, "entry", "stock", second)
    assert db2.statement.compile().params["data_fingerprint"] != fp1


def test_market_reconstruction_explains_saved_warnings_and_returns_dated_index_phase(monkeypatch):
    from datetime import timedelta
    from app.db.models import MarketSnapshot, PriceBar
    from app.services import trade_journal_backfill as service

    day = date(2026, 9, 21)
    bars = [PriceBar(date=day - timedelta(days=259-i), open=100+i/10,
                     high=101+i/10, low=99+i/10, close=100+i/10,
                     volume=100000+i*100, source="test") for i in range(260)]
    snapshot = MarketSnapshot(date=day, ampel_phase="rot", warning_count=5,
        volatility_regime="Risk On / ruhig", metrics_json={
            "pct_above_50sma": 34.7, "pct_above_200sma": 44.5,
            "mcclellan": -21.5, "advancers": 2851, "decliners": 2406,
            "new_highs": 80, "new_lows": 199, "coverage_ratio": 0.974,
            "margin_debt": {"warning_active": True, "margin_debt_ratio_pct": 77.4},
        })

    class Database:
        def __init__(self, snapshot):
            self.values = iter([None, snapshot, None, None])
        def scalar(self, statement):
            return next(self.values)

    monkeypatch.setattr(service, "_bars_for_ticker", lambda *args: bars)
    context = service._market_context(Database(snapshot), day,
                                     datetime(2026, 9, 21, 23, 59, tzinfo=UTC))
    payload = context["payload"]
    assert payload["trend"]["as_of"] == day.isoformat()
    assert payload["trend"]["phase_label"]
    assert sum(check["active_warning"] for check in payload["market_warning_checks"]) == 5
    assert all(check["detail"] for check in payload["market_warning_checks"])
    # A phase is still reconstructed from dated index prices without a stored snapshot.
    missing_snapshot = service._market_context(Database(None), day,
                                     datetime(2026, 9, 21, 23, 59, tzinfo=UTC))
    assert missing_snapshot["payload"]["trend"]["phase"] == payload["trend"]["phase"]
    assert "market_snapshot_missing" in missing_snapshot["reason_codes"]
