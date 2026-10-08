import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_beta_compose_has_same_image_and_no_private_environment_or_extra_infrastructure(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose required for config verification")
    shutil.copy(ROOT / "infra/docker-compose.nas.yml", tmp_path / "compose.yml")
    env = (ROOT / "infra/.env.nas.example").read_text() + "\nPOSTGRES_PASSWORD=test-only\nCOMPOSE_PROFILES=beta\n"
    (tmp_path / ".env.nas").write_text(env)
    result = subprocess.run(["docker", "compose", "--env-file", ".env.nas", "-f", "compose.yml", "--profile", "beta", "--profile", "migrate", "config", "--format", "json"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    beta = services["frontend-beta"]
    assert beta["image"] == services["frontend"]["image"]
    assert beta["profiles"] == ["beta"]
    assert "volumes" not in beta
    assert set(beta["environment"]) == {"API_INTERNAL_BASE_URL", "APP_BETA_MODE", "BETA_ACCESS_MODE",
                                        "BETA_PUBLIC_ENABLED", "BETA_PUBLIC_ORIGIN", "BETA_AUTH_PASSWORD", "BETA_PROXY_SECRET",
                                        "NODE_OPTIONS", "NEXT_TELEMETRY_DISABLED"}
    assert beta["environment"]["APP_BETA_MODE"] == "1"
    assert services["frontend"]["environment"]["APP_BETA_MODE"] == "0"
    assert beta["ports"][0]["host_ip"] == "127.0.0.1"
    assert beta["ports"][0]["published"] == "3001"
    assert set(beta["depends_on"]) == {"backend"}
    assert sum(name == "postgres" for name in services) == 1
    assert sum(name == "scheduler" for name in services) == 1
    assert set(services) == {"postgres", "redis", "migrate", "backend", "worker", "report-worker", "interactive-worker", "monitor", "scheduler", "frontend", "frontend-beta"}


@pytest.mark.parametrize("active", [False, True])
def test_update_keeps_active_beta_and_runs_one_migration_without_orphan_removal(tmp_path, active):
    (tmp_path / ".env.nas").write_text("IMAGE_TAG=test-only\n")
    trace = tmp_path / "trace.txt"
    docker = tmp_path / "docker"
    docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$TRACE"
case "$*" in
  *"ps --status running -q frontend-beta"*) [ "$BETA_TEST_ACTIVE" = 1 ] && printf 'fixture-beta-container\\n';;
esac
exit 0
''')
    docker.chmod(0o755)
    env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "TRACE": str(trace), "BETA_TEST_ACTIVE": "1" if active else "0"}
    result = subprocess.run(["sh", str(ROOT / "infra/update-nas.sh")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = trace.read_text().splitlines()
    assert sum(call.endswith("run --rm migrate") for call in calls) == 1
    assert not any("--remove-orphans" in call for call in calls)
    for action in ["pull", "up -d"]:
        call = next(call for call in calls if call.endswith(action))
        assert ("--profile beta" in call) is active


def test_frontend_beta_entrypoint_cannot_import_private_runtime_file(tmp_path):
    private = tmp_path / "runtime.env"
    private.write_text("APP_AUTH_PASSWORD=private-fixture\n")
    command = ["sh", str(ROOT / "frontend/docker-entrypoint.sh"), "sh", "-c", 'test -z "${APP_AUTH_PASSWORD:-}"']
    env = {**os.environ, "APP_BETA_MODE": "1", "APP_RUNTIME_ENV_FILE": str(private)}
    env.pop("APP_AUTH_PASSWORD", None)
    assert subprocess.run(command, env=env).returncode == 0
    env["APP_BETA_MODE"] = "0"
    assert subprocess.run(command, env=env).returncode != 0
