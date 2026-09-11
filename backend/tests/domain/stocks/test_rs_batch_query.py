from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories import relative_strength as repository


@pytest.mark.parametrize("source", [None, "computed", "csv_latest"])
def test_batch_rs_query_limits_history_before_loading_metadata(monkeypatch, source):
    session = MagicMock()
    session.__enter__.return_value = session
    rating = object()
    instrument = SimpleNamespace(ticker="AAPL")
    session.execute.return_value.all.return_value = [(rating, instrument)]
    monkeypatch.setattr(repository, "SessionLocal", lambda: session)
    monkeypatch.setattr(repository, "_row_to_dataclass", lambda *_: "latest")

    assert repository.get_latest_rs_ratings_for_tickers([" aapl ", "AAPL"], source=source) == {"AAPL": "latest"}

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "DISTINCT ON" not in sql
    assert "rs_ratings.id = (SELECT rs_ratings.id" in sql
    assert "rs_ratings.instrument_id = instruments.id" in sql
    assert "ORDER BY rs_ratings.date DESC" in sql
    assert "LIMIT 1" in sql
    assert "instruments.ticker IN ('AAPL')" in sql
    if source:
        assert f"rs_ratings.source = '{source}'" in sql


def test_empty_batch_does_not_connect(monkeypatch):
    connect = MagicMock(side_effect=AssertionError("No connection expected"))
    monkeypatch.setattr(repository, "SessionLocal", connect)
    assert repository.get_latest_rs_ratings_for_tickers([]) == {}
    connect.assert_not_called()
