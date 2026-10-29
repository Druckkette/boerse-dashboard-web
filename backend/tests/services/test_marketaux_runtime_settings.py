from copy import deepcopy

import pytest

from app.beta_policy import beta_api_allowed
from app.core_config import Settings
from app.schemas import RuntimeConfigPatch, RuntimeConfigTestRequest
from app.services import settings as service


FIRST_KEY = "test-only-marketaux-first-credential"
SECOND_KEY = "test-only-marketaux-second-credential"
ENV_KEY = "test-only-marketaux-environment-credential"


@pytest.fixture
def store(monkeypatch):
    persisted = {}
    runtime = Settings(marketaux_api_key="")
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)
    monkeypatch.setattr(service, "get_settings", lambda: runtime)
    monkeypatch.setattr(service.settings_repository, "read_runtime_config", lambda: deepcopy(persisted))

    def patch(values, clear_keys):
        for key in clear_keys:
            persisted.pop(key, None)
        persisted.update(values)
        return deepcopy(persisted)

    monkeypatch.setattr(service.settings_repository, "patch_runtime_config", patch)
    return persisted, runtime


def item(response):
    return next(row for row in response.items if row.key == "MARKETAUX_API_KEY")


def test_ui_secret_is_stored_but_read_and_patch_responses_are_fully_masked(store, monkeypatch):
    persisted, _ = store

    def forbidden(*args):
        raise AssertionError("Marketaux-only edits must not touch the shared runtime-env file")

    monkeypatch.setattr(service, "_write_runtime_env_file", forbidden)
    assert not item(service.get_runtime_config()).configured
    response = service.update_runtime_config(RuntimeConfigPatch(values={"MARKETAUX_API_KEY": FIRST_KEY}))
    configured = item(response)
    assert persisted["MARKETAUX_API_KEY"] == FIRST_KEY
    assert configured.configured and configured.secret and configured.editable
    assert configured.runtime_applied and not configured.restart_required
    assert configured.source == "database" and configured.value_preview == "********"
    assert FIRST_KEY not in response.model_dump_json()
    assert FIRST_KEY not in service.get_runtime_config().model_dump_json()
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == FIRST_KEY
    # Both responses hide the entire key, including its prefix, suffix and length.
    second = service.update_runtime_config(RuntimeConfigPatch(values={"MARKETAUX_API_KEY": SECOND_KEY}))
    assert item(second).value_preview == configured.value_preview
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == SECOND_KEY


def test_secret_is_never_mirrored_even_when_other_runtime_values_are_saved(store, monkeypatch, tmp_path):
    persisted, _ = store
    persisted["MARKETAUX_API_KEY"] = FIRST_KEY
    path = tmp_path / "runtime.env"
    monkeypatch.setenv("APP_RUNTIME_ENV_FILE", str(path))
    service.update_runtime_config(RuntimeConfigPatch(values={"SEC_USER_AGENT": "test contact@example.org"}))
    assert "SEC_USER_AGENT=" in path.read_text()
    assert "MARKETAUX" not in path.read_text() and FIRST_KEY not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600


def test_clearing_db_override_does_not_need_file_write_or_restart(store, monkeypatch):
    persisted, _ = store
    persisted["MARKETAUX_API_KEY"] = FIRST_KEY
    monkeypatch.setattr(service, "_write_runtime_env_file", lambda *a: pytest.fail("Unexpected shared file write"))
    response = service.update_runtime_config(RuntimeConfigPatch(clear_keys=["MARKETAUX_API_KEY"]))
    assert "MARKETAUX_API_KEY" not in persisted
    assert not item(response).configured and item(response).source == "missing"
    assert item(response).value_preview == ""
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == ""


def test_secretstr_environment_value_is_unwrapped_only_internally_and_masked_in_ui(store, monkeypatch):
    persisted, _ = store
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key=ENV_KEY))
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == ENV_KEY
    env_item = item(service.get_runtime_config())
    assert env_item.source == "environment" and env_item.configured
    assert env_item.value_preview == "********"
    assert ENV_KEY not in service.get_runtime_config().model_dump_json()
    persisted["MARKETAUX_API_KEY"] = FIRST_KEY
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == FIRST_KEY
    response = service.update_runtime_config(RuntimeConfigPatch(clear_keys=["MARKETAUX_API_KEY"]))
    assert item(response).source == "environment" and item(response).value_preview == "********"
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == ENV_KEY


def test_explicit_environment_fallback_and_database_override_priority(store, monkeypatch):
    persisted, _ = store
    monkeypatch.setenv("MARKETAUX_API_KEY", ENV_KEY)
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == ENV_KEY
    persisted["MARKETAUX_API_KEY"] = FIRST_KEY
    assert service.get_runtime_config_value("MARKETAUX_API_KEY") == FIRST_KEY


@pytest.mark.parametrize("value,expected", [(FIRST_KEY, "ok"), ("", "missing"), ("too short", "invalid")])
def test_format_check_never_calls_provider_or_reserves_quota(store, monkeypatch, value, expected):
    monkeypatch.setattr(service.requests, "get", lambda *a, **kw: pytest.fail("No external format-test request"))
    response = service.test_runtime_config(RuntimeConfigTestRequest(key="MARKETAUX_API_KEY", value=value))
    assert response.status == expected and response.ok == (expected == "ok")
    assert FIRST_KEY not in response.model_dump_json()
    if expected == "ok":
        assert "lokal" in response.detail and "Keine Anbieteranfrage" in response.detail


def test_marketaux_secret_settings_remain_forbidden_to_beta():
    assert not beta_api_allowed("GET", "settings/runtime-config")
    assert not beta_api_allowed("PATCH", "settings/runtime-config")
    assert not beta_api_allowed("POST", "settings/runtime-config/test")
