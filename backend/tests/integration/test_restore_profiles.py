"""Exercise the real recovery script with disposable Compose projects and dumps."""
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.environ.get("TEST_DOCKER_RESTORE") != "1", reason="Disposable Docker restore test not enabled")


@pytest.mark.parametrize("profile", ["nas", "hetzner"])
def test_real_restore_uses_only_services_in_selected_profile(tmp_path, profile):
    project = "dashboard-restore-audit-" + uuid4().hex[:8]
    env_file = f".env.{profile}"
    compose_file = f"docker-compose.{profile}.yml"
    shutil.copy(ROOT / "infra" / compose_file, tmp_path / compose_file)
    shutil.copy(ROOT / "infra" / (env_file + ".example"), tmp_path / env_file)
    app_names = ["backend", "worker", "interactive-worker", "monitor", "scheduler", "frontend"]
    if profile == "nas":
        app_names += ["frontend-beta", "report-worker"]
    # Reset mounts/ports instead of inheriting the NAS Docker socket or exposing
    # any application. The original service graph/names remain under test.
    override_text = "services:\n"
    for name in app_names:
        override_text += f"  {name}:\n    image: alpine:latest\n    entrypoint: []\n    command: [sleep, infinity]\n    ports: !reset []\n    volumes: !reset []\n    healthcheck:\n      test: [CMD, 'true']\n      interval: 1s\n"
    (tmp_path / "override.yml").write_text(override_text)
    environment = {**os.environ, "POSTGRES_DB": "audit_tests", "POSTGRES_USER": "audit", "POSTGRES_PASSWORD": "audit", "IMAGE_TAG": "test", "COMPOSE_PROFILES": "beta" if profile == "nas" else ""}
    environment.update(COMPOSE_FILE=f"{compose_file}:override.yml", COMPOSE_PROJECT_NAME=project, ENV_FILE=env_file)
    rendered = subprocess.run(["docker", "compose", "--env-file", env_file, "--profile", "*", "config"],
                              cwd=tmp_path, env=environment, capture_output=True, check=True).stdout
    (tmp_path / "restore-compose.yml").write_bytes(rendered)
    environment["COMPOSE_FILE"] = "restore-compose.yml"
    def compose(*args, **kwargs):
        return subprocess.run(["docker", "compose", "--env-file", env_file, *args], cwd=tmp_path,
                              env=environment, check=True, capture_output=True, **kwargs)
    def sql(statement):
        return compose("exec", "-T", "postgres", "psql", "-U", "audit", "-d", "audit_tests", "-Atc", statement).stdout.strip()
    try:
        compose("up", "-d", "--wait", "--wait-timeout", "60", "postgres", "backend", "worker")
        sql("CREATE TABLE audit_restore_probe (id integer PRIMARY KEY, note text); INSERT INTO audit_restore_probe VALUES (1,'restored')")
        dump = compose("exec", "-T", "postgres", "pg_dump", "-U", "audit", "-d", "audit_tests", "-Fc").stdout
        (tmp_path / "backup.dump").write_bytes(dump)
        sql("DROP TABLE audit_restore_probe")
        result = subprocess.run(["sh", str(ROOT / "infra/restore-postgres.sh"), "backup.dump"], cwd=tmp_path,
                                env={**environment, "RESTORE_CONFIRM": "I_UNDERSTAND_THIS_OVERWRITES_DATABASE",
                                     "RUN_MIGRATIONS_AFTER_RESTORE": "0", "START_SERVICES_AFTER_RESTORE": "0"},
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert sql("SELECT note FROM audit_restore_probe WHERE id=1") == b"restored"
        running = compose("ps", "--status", "running", "--services").stdout.decode().splitlines()
        assert set(running) == {"postgres", "redis"}
    finally:
        compose("down", "--volumes", "--remove-orphans")
