"""Exercise the NAS helper against isolated files; never contact or reload a NAS."""

import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "infra/nas-beta-http-redirect.sh"


@pytest.fixture
def redirect(tmp_path, monkeypatch):
    source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    namespace = {"__name__": "beta_redirect_test"}
    exec(compile(source, str(SCRIPT), "exec"), namespace)
    base = tmp_path.resolve()
    for name, relative in (
        ("RULES", "ReverseProxy.json"),
        ("VHOSTS", "server.ReverseProxy.conf"),
        ("PROFILE", "tls/beta.conf"),
        ("BACKUPS", "backups"),
        ("LOCK", "lock"),
    ):
        namespace[name] = base / relative
    namespace["INCLUDE"] = Path(str(namespace["PROFILE"]) + ".boerse-http-redirect")
    namespace["PROFILE"].parent.mkdir()
    namespace["PROFILE"].write_text("ssl_protocols TLSv1.2 TLSv1.3;\n")
    rules = {
        namespace["RULE_ID"]: {
            "frontend": {"fqdn": namespace["HOST"], "port": 3001, "protocol": 1},
            "backend": {"fqdn": "127.0.0.1", "port": 3002, "protocol": 0},
        }
    }
    namespace["RULES"].write_text(json.dumps(rules))
    block = (
        "server {\n listen 3001 ssl;\n listen [::]:3001 ssl;\n server_name "
        + namespace["HOST"]
        + ";\n include "
        + str(namespace["PROFILE"])
        + '*;\n proxy_set_header X-Test "literal { } # quoted";\n'
        " location / { proxy_pass http://127.0.0.1:3002; }\n"
        " error_page 403 404 500 /dsm_error_page;\n}\n"
    )
    namespace["VHOSTS"].write_text(block)

    # Simulate root ownership only for fixture files, including on macOS /private paths.
    # Actual file types and permission bits remain available to the safety guards.
    def root_owned(original):
        def inspect(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if str(path).startswith(str(base)):
                fields = list(info)
                fields[4] = 0
                return os.stat_result(fields)
            return info

        return inspect

    monkeypatch.setattr(Path, "stat", root_owned(Path.stat))
    monkeypatch.setattr(Path, "lstat", root_owned(Path.lstat))
    original_fstat = os.fstat

    def root_fstat(descriptor):
        fields = list(original_fstat(descriptor))
        fields[4] = 0
        return os.stat_result(fields)

    monkeypatch.setattr(os, "fstat", root_fstat)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(namespace["shutil"], "which", lambda name: "/usr/sbin/nginx")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, "", "nginx version: nginx/1.23.1"
        ),
    )
    calls = []
    namespace["nginx_command"] = lambda nginx, *arguments: calls.append(arguments)
    namespace["live_redirect"] = lambda: (
        namespace["INCLUDE"].exists()
        and namespace["INCLUDE"].read_bytes() == namespace["CONTENT"]
    )
    return SimpleNamespace(namespace=namespace, block=block, rules=rules, calls=calls)


def test_quoted_braces_and_comments_do_not_confuse_beta_target(redirect):
    ns = redirect.namespace
    ns["VHOSTS"].write_text("# server { listen 3001 ssl; }\n" + redirect.block)
    ns["inspect_target"]()


def test_default_check_does_not_create_lock_backup_or_include(redirect, monkeypatch, capsys):
    ns = redirect.namespace
    monkeypatch.setattr("sys.argv", ["nas-beta-http-redirect.sh"])
    ns["main"]()
    assert json.loads(capsys.readouterr().out)["read_only"] is True
    assert not any(ns[key].exists() for key in ("INCLUDE", "BACKUPS", "LOCK"))


def test_different_proxy_metadata_is_rejected(redirect):
    ns = redirect.namespace
    redirect.rules[ns["RULE_ID"]]["backend"]["port"] = 443
    ns["RULES"].write_text(json.dumps(redirect.rules))
    with pytest.raises(RuntimeError, match="Beta-Ziel"):
        ns["inspect_target"]()


def test_duplicate_beta_server_is_rejected(redirect):
    ns = redirect.namespace
    ns["VHOSTS"].write_text(redirect.block + redirect.block)
    with pytest.raises(RuntimeError, match="genau ein"):
        ns["inspect_target"]()


def test_include_shared_with_another_host_is_rejected(redirect):
    ns = redirect.namespace
    ns["VHOSTS"].write_text(
        redirect.block + "server { listen 443 ssl; include " + str(ns["PROFILE"]) + "*; }"
    )
    with pytest.raises(RuntimeError, match="ausschließlich"):
        ns["inspect_target"]()


def test_existing_foreign_redirect_rule_is_rejected(redirect):
    ns = redirect.namespace
    ns["VHOSTS"].write_text(
        redirect.block.replace(
            "error_page 403", "error_page 497 =301 https://other.invalid;\n error_page 403"
        )
    )
    with pytest.raises(RuntimeError, match="andere 497"):
        ns["inspect_target"]()


def test_foreign_companion_is_not_overwritten(redirect):
    ns = redirect.namespace
    content = "error_page 497 =301 https://other.invalid;\n"
    ns["INCLUDE"].write_text(content)
    with pytest.raises(RuntimeError, match="fremd verändert"):
        ns["inspect_target"]()
    assert ns["INCLUDE"].read_text() == content


def test_group_or_world_writable_profile_is_rejected(redirect):
    ns = redirect.namespace
    ns["PROFILE"].chmod(0o666)
    with pytest.raises(RuntimeError, match="root-eigene"):
        ns["inspect_target"]()


def test_apply_is_idempotent_and_preserves_generated_vhost_and_tls_profile(redirect):
    ns = redirect.namespace
    profile_before = ns["PROFILE"].read_bytes()
    ns["mutate"]("apply")
    ns["mutate"]("apply")
    assert ns["VHOSTS"].read_text() == redirect.block
    assert ns["PROFILE"].read_bytes() == profile_before
    assert ns["INCLUDE"].read_bytes() == ns["CONTENT"]
    assert redirect.calls.count(("-s", "reload")) == 1
    assert stat.S_IMODE(ns["INCLUDE"].stat().st_mode) == 0o600
    backups = list(ns["BACKUPS"].iterdir())
    assert len(backups) == 1
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o700
    assert stat.S_IMODE((backups[0] / "beta-server-before.conf").stat().st_mode) == 0o600


def test_invalid_new_configuration_is_removed_without_reload(redirect):
    ns = redirect.namespace

    def command(nginx, *arguments):
        redirect.calls.append(arguments)
        if arguments == ("-t",) and ns["INCLUDE"].exists():
            raise RuntimeError("mock invalid configuration")

    ns["nginx_command"] = command
    with pytest.raises(RuntimeError, match="mock invalid"):
        ns["mutate"]("apply")
    assert not ns["INCLUDE"].exists()
    assert ("-s", "reload") not in redirect.calls
    assert ns["VHOSTS"].read_text() == redirect.block


def test_failed_reload_restores_and_reloads_previous_state(redirect):
    ns = redirect.namespace

    def command(nginx, *arguments):
        redirect.calls.append(arguments)
        if arguments == ("-s", "reload") and redirect.calls.count(arguments) == 1:
            raise RuntimeError("mock reload failed")

    ns["nginx_command"] = command
    with pytest.raises(RuntimeError, match="mock reload"):
        ns["mutate"]("apply")
    assert not ns["INCLUDE"].exists()
    assert redirect.calls.count(("-s", "reload")) == 2


def test_failed_live_redirect_probe_rolls_back(redirect, monkeypatch):
    ns = redirect.namespace
    ns["live_redirect"] = lambda: False
    monkeypatch.setattr(ns["time"], "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="nicht aktiv"):
        ns["mutate"]("apply")
    assert not ns["INCLUDE"].exists()
    assert redirect.calls.count(("-s", "reload")) == 2


def test_remove_only_removes_managed_companion_and_is_idempotent(redirect):
    ns = redirect.namespace
    ns["mutate"]("apply")
    ns["mutate"]("remove")
    ns["mutate"]("remove")
    assert not ns["INCLUDE"].exists()
    assert ns["VHOSTS"].read_text() == redirect.block
    assert redirect.calls.count(("-s", "reload")) == 2


def test_new_backup_directories_with_inherited_open_permissions_are_restricted(redirect, monkeypatch):
    ns = redirect.namespace
    original_mkdir = Path.mkdir
    original_mkdtemp = ns["tempfile"].mkdtemp

    def inherited_mkdir(path, *args, **kwargs):
        original_mkdir(path, *args, **kwargs)
        if path == ns["BACKUPS"]:
            path.chmod(0o777)

    def inherited_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        Path(path).chmod(0o777)
        return path

    monkeypatch.setattr(Path, "mkdir", inherited_mkdir)
    monkeypatch.setattr(ns["tempfile"], "mkdtemp", inherited_mkdtemp)
    ns["mutate"]("apply")
    assert stat.S_IMODE(ns["BACKUPS"].stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in ns["BACKUPS"].iterdir())


def test_existing_open_backup_directory_is_rejected_without_chmod_or_nginx_change(redirect):
    ns = redirect.namespace
    ns["BACKUPS"].mkdir()
    ns["BACKUPS"].chmod(0o777)
    with pytest.raises(RuntimeError, match="Modus 0700"):
        ns["mutate"]("apply")
    assert stat.S_IMODE(ns["BACKUPS"].stat().st_mode) == 0o777
    assert not ns["INCLUDE"].exists()
    assert ("-s", "reload") not in redirect.calls


def test_backup_symlink_is_rejected_without_changing_target_permissions(redirect):
    ns = redirect.namespace
    target = ns["BACKUPS"].with_name("foreign-directory")
    target.mkdir()
    target.chmod(0o777)
    ns["BACKUPS"].symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError, match="ohne Symlink"):
        ns["mutate"]("apply")
    assert stat.S_IMODE(target.stat().st_mode) == 0o777
    assert not ns["INCLUDE"].exists()
