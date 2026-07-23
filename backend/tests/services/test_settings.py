from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import settings as settings_service


def test_database_target_migration_uses_selected_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(settings_service.subprocess, "run", fake_run)

    settings_service._migrate_database_target("postgresql+psycopg://user:secret@neon.example/db")

    assert calls[0]["command"] == ["alembic", "upgrade", "head"]
    assert calls[0]["env"]["DATABASE_URL"] == "postgresql+psycopg://user:secret@neon.example/db"
    assert calls[0]["timeout"] == 300
    assert calls[0]["check"] is False


def test_database_target_migration_does_not_expose_url_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+psycopg://user:top-secret@neon.example/db"
    monkeypatch.setattr(
        settings_service.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=f"connection failed for {database_url}",
        ),
    )

    with pytest.raises(ValueError) as exc_info:
        settings_service._migrate_database_target(database_url)

    assert "top-secret" not in str(exc_info.value)
    assert "<database-url>" in str(exc_info.value)
