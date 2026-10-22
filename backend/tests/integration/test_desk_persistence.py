"""Real PostgreSQL persistence/concurrency; refuses to use an application database."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting
from app.domain.desk import Watchlist
from app.repositories import desk, workspace
from app.services import desk as service

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured"
)


@pytest.fixture
def database(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    for module in (desk, workspace):
        monkeypatch.setattr(module, "SessionLocal", sessions)
    with sessions() as db:
        db.execute(delete(AppSetting).where(AppSetting.key.in_([desk.KEY, "workspace"])))
        db.add(
            AppSetting(
                key="workspace",
                value_json={
                    "watchlist": ["NVDA"],
                    "todos": "Bestehende Notiz",
                    "recent_tickers": ["AAPL"],
                },
            )
        )
        db.commit()
    yield sessions
    with sessions() as db:
        db.execute(delete(AppSetting).where(AppSetting.key.in_([desk.KEY, "workspace"])))
        db.commit()
    engine.dispose()


def test_existing_workspace_survives_and_new_lists_are_read_by_fresh_sessions(database):
    assert service.state()["watchlists"][0]["items"][0]["ticker"] == "NVDA"
    service.save(
        "watchlists",
        Watchlist(name="Branchenführer", items=[dict(ticker="MSFT", note="Nach Earnings prüfen")]),
        revision=0,
    )
    assert service.state()["watchlists"][1]["items"][0]["note"] == "Nach Earnings prüfen"
    legacy, _ = workspace.read_workspace()
    assert legacy["todos"] == "Bestehende Notiz"
    assert legacy["recent_tickers"] == ["AAPL"]
    assert legacy["watchlist"] == ["NVDA"]
    # Existing recent-ticker writes preserve the new tracking metadata.
    workspace.write_workspace({"recent_tickers": ["TSLA"]})
    assert "MSFT" in workspace.read_workspace()[0]["tracked_watchlists"]


def test_concurrent_revision_writes_allow_exactly_one_and_preserve_the_winner(database):
    def write(name):
        try:
            service.save("watchlists", Watchlist(name=name), revision=0)
            return "saved"
        except desk.DeskConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ["Liste A", "Liste B"]))
    assert sorted(outcomes) == ["conflict", "saved"]
    assert service.state()["revision"] == 1
    assert len(service.state()["watchlists"]) == 2


def test_failed_mutation_rolls_back_all_collections(database):
    def invalid(value):
        value["watchlists"].append(dict(id="bad", name="Nicht speichern", items=[]))
        raise ValueError("Abbruch vor Commit")

    with pytest.raises(ValueError):
        desk.transact(invalid, revision=0)
    assert service.state()["revision"] == 0
    assert len(service.state()["watchlists"]) == 1


def test_legacy_favorites_remain_live_without_resurrecting_removed_tickers(database):
    favorites = Watchlist(name="Favoriten", items=[dict(ticker="NVDA", note="Eigene Prüfung")])
    service.save("watchlists", favorites, item_id="default", revision=0)
    assert service.state()["watchlists"][0]["name"] == "Favoriten"
    workspace.write_workspace({"watchlist": ["NVDA", "MSFT"]})
    with pytest.raises(desk.DeskConflict):
        service.save("watchlists", favorites, item_id="default", revision=1)
    current = service.state()["watchlists"][0]
    assert current["items"][0]["note"] == "Eigene Prüfung"
    assert current["items"][1]["ticker"] == "MSFT"
    workspace.write_workspace({"watchlist": []})
    assert service.state()["watchlists"][0]["items"] == []
