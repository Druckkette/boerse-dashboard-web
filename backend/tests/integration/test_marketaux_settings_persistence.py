"""Runtime secret writes use the existing DB and never the frontend-shared file."""
from copy import deepcopy
import os

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core_config import Settings
from app.db.models import AppSetting
from app.schemas import RuntimeConfigPatch
from app.services import settings as service


pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")
KEYS = ["runtime_config", "marketaux:budget:v1", "marketaux:news:v1:test-settings"]


@pytest.fixture
def database(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests", "Never use an application database"
    engine = create_engine(url)
    AppSetting.__table__.create(engine, checkfirst=True)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(service.settings_repository, "SessionLocal", sessions)
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key=""))
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)
    # Marketaux-only changes must succeed without access to the shared volume.
    monkeypatch.setenv("APP_RUNTIME_ENV_FILE", "/dev/null/not-a-directory/runtime.env")
    with sessions() as db:
        before = {key: deepcopy(row.value_json) if (row := db.get(AppSetting, key)) else None for key in KEYS}
        db.execute(delete(AppSetting).where(AppSetting.key.in_(KEYS)))
        db.add_all([
            AppSetting(key="marketaux:budget:v1", value_json={"attempts": ["2026-10-29T10:00:00+00:00"]}),
            AppSetting(key="marketaux:news:v1:test-settings", value_json={"articles": [], "updated_at": "2026-10-29T10:00:00+00:00"}),
        ])
        db.commit()
    yield engine, sessions
    with sessions() as db:
        db.execute(delete(AppSetting).where(AppSetting.key.in_(KEYS)))
        for key, value in before.items():
            if value is not None:
                db.add(AppSetting(key=key, value_json=value))
        db.commit()
    engine.dispose()


def test_saved_key_persists_after_connection_restart_changes_immediately_and_keeps_budget_cache(database):
    engine, sessions = database
    first = "test-only-first-persisted-marketaux-key"
    second = "test-only-second-persisted-marketaux-key"
    result = service.update_runtime_config(RuntimeConfigPatch(values={"MARKETAUX_API_KEY": first}))
    selected = next(item for item in result.items if item.key == "MARKETAUX_API_KEY")
    assert selected.configured and selected.value_preview == "********"
    assert first not in result.model_dump_json()
    engine.dispose()
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == first
    service.update_runtime_config(RuntimeConfigPatch(values={"MARKETAUX_API_KEY": second}))
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == second
    with sessions() as db:
        assert db.get(AppSetting, "runtime_config").value_json["MARKETAUX_API_KEY"] == second
        assert db.get(AppSetting, "marketaux:budget:v1").value_json == {"attempts": ["2026-10-29T10:00:00+00:00"]}
        assert db.get(AppSetting, "marketaux:news:v1:test-settings").value_json["updated_at"] == "2026-10-29T10:00:00+00:00"
    service.update_runtime_config(RuntimeConfigPatch(clear_keys=["MARKETAUX_API_KEY"]))
    engine.dispose()
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == ""
    assert not next(item for item in service.get_runtime_config().items if item.key == "MARKETAUX_API_KEY").configured
