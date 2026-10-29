#!/bin/sh
# Default is read-only. Apply/remove only after reviewing the NAS-specific guards.
set -eu
export PATH=/usr/local/bin:/usr/bin:/usr/sbin:$PATH
exec python3 - "$@" <<'PY'
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time


RULE_ID = "5edae515-2b91-4360-8f8a-cb42290ad2c3"
HOST = "fumificate.myds.me"
ORIGIN = "https://fumificate.myds.me:3001"
RULES = Path("/usr/syno/etc/www/ReverseProxy.json")
VHOSTS = Path("/etc/nginx/sites-enabled/server.ReverseProxy.conf")
PROFILE = Path("/usr/syno/etc/security-profile/tls-profile/config") / ("ReverseProxy_" + RULE_ID + ".conf")
INCLUDE = Path(str(PROFILE) + ".boerse-http-redirect")
BACKUPS = Path("/volume1/docker/boerse-dashboard-web/infra/backups/beta-http-redirect")
LOCK = Path("/run/boerse-beta-http-redirect.lock")
CONTENT = (
    "# Managed by boerse-dashboard-web/infra/nas-beta-http-redirect.sh\n"
    "# Only the guarded beta reverse-proxy server includes this file.\n"
    "error_page 497 =308 https://fumificate.myds.me:3001$request_uri;\n"
).encode()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def parse_nginx(source):
    """Read directives/blocks; quoted strings, escaped characters and comments are tokens."""
    token = re.compile(r'''\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{};]|(?:\\.|[^\s{};\#"'])+''')
    tokens = []
    for match in token.finditer(source):
        value = match.group()
        if value.isspace() or value.startswith("#"):
            continue
        if value[:1] in ("'", '"'):
            value = value[1:-1]
        tokens.append((value, match.start(), match.end()))
    root = []
    stack = [root]
    pending = []
    for value, start, end in tokens:
        if value in (";", "{"):
            require(bool(pending), "Ungültige nginx-Direktive; keine Änderung.")
            node = {"words": [word[0] for word in pending], "start": pending[0][1], "end": end, "children": None}
            stack[-1].append(node)
            pending = []
            if value == "{":
                node["children"] = []
                stack.append(node["children"])
        elif value == "}":
            require(not pending and len(stack) > 1, "Unvollständiger nginx-Block; keine Änderung.")
            stack.pop()
            stack[-1][-1]["end"] = end
        else:
            pending.append((value, start, end))
    require(len(stack) == 1 and not pending, "Unvollständige nginx-Konfiguration; keine Änderung.")
    return root


def walk(nodes):
    for node in nodes:
        yield node
        if node["children"] is not None:
            yield from walk(node["children"])


def ordinary_root_file(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            "Erwartete reguläre, root-eigene Datei ohne fremde Schreibrechte: " + str(path))
    return info


def inspect_target():
    require(os.geteuid() == 0, "Das Skript muss als root ausgeführt werden.")
    rule = json.loads(RULES.read_text()).get(RULE_ID, {})
    front, back = rule.get("frontend", {}), rule.get("backend", {})
    require((front.get("fqdn"), front.get("port"), front.get("protocol")) == (HOST, 3001, 1),
            "Die Beta-Quelle stimmt nicht mehr mit HTTPS fumificate.myds.me:3001 überein.")
    require((back.get("fqdn"), back.get("port"), back.get("protocol")) == ("127.0.0.1", 3002, 0),
            "Das Beta-Ziel stimmt nicht mehr mit HTTP 127.0.0.1:3002 überein.")
    ordinary_root_file(VHOSTS.resolve(strict=True))
    ordinary_root_file(PROFILE)
    require(PROFILE.parent.stat().st_uid == 0 and not PROFILE.parent.stat().st_mode & 0o022,
            "Das Include-Verzeichnis ist nicht ausreichend geschützt.")
    source = VHOSTS.read_text()
    nodes = parse_nginx(source)
    servers = [node for node in walk(nodes) if node["words"] == ["server"] and node["children"] is not None]
    matches = []
    for server in servers:
        directives = [node["words"] for node in server["children"]]
        names = [words[1:] for words in directives if words[0] == "server_name"]
        listens = [words[1:] for words in directives if words[0] == "listen"]
        if [HOST] in names and any(words and words[0] in ("3001", "[::]:3001") for words in listens):
            matches.append(server)
    require(len(matches) == 1, "Erwartet wird genau ein kanonischer Beta-Serverblock.")
    server = matches[0]
    directives = [node["words"] for node in server["children"]]
    listens = [words[1:] for words in directives if words[0] == "listen"]
    require({words[0] for words in listens} == {"3001", "[::]:3001"} and all("ssl" in words for words in listens),
            "Der Beta-Block besitzt nicht die erwarteten IPv4-/IPv6-TLS-Listener.")
    wildcard = str(PROFILE) + "*"
    includes = [node for node in walk(nodes) if node["words"] == ["include", wildcard]]
    require(len(includes) == 1 and includes[0] in server["children"],
            "Der regelbezogene Include muss ausschließlich direkt im Beta-Serverblock stehen.")
    proxy = [node["words"] for node in walk(server["children"]) if node["words"][0] == "proxy_pass"]
    require(proxy == [["proxy_pass", "http://127.0.0.1:3002"]], "Unerwartetes Beta-Upstreamziel.")
    require(not any(node["words"][0] == "error_page" and "497" in node["words"][1:]
                    for node in walk(server["children"])), "Im Beta-Block existiert bereits eine andere 497-Regel.")
    for path in PROFILE.parent.glob(PROFILE.name + "*"):
        ordinary_root_file(path)
        if path == INCLUDE:
            require(path.read_bytes() == CONTENT, "Die Begleitdatei wurde fremd verändert; keine Überschreibung.")
        else:
            require(not any(node["words"][0] == "error_page" and "497" in node["words"][1:]
                            for node in walk(parse_nginx(path.read_text()))),
                    "Eine andere TLS-Profil-Datei enthält bereits eine 497-Regel.")
    nginx = shutil.which("nginx")
    require(bool(nginx), "nginx wurde nicht gefunden.")
    version = subprocess.run([nginx, "-v"], capture_output=True, text=True)
    match = re.search(r"nginx/(\d+)\.(\d+)", version.stderr + version.stdout)
    require(version.returncode == 0 and match and tuple(map(int, match.groups())) >= (1, 13),
            "nginx ab Version 1.13 wird für den 308-Redirect benötigt.")
    return nginx, source[server["start"]:server["end"]]


def live_redirect():
    connection = http.client.HTTPConnection("127.0.0.1", 3001, timeout=3)
    path = "/chart-analysis?beta_redirect_probe=1"
    try:
        connection.request("GET", path, headers={"Host": HOST + ":3001"})
        response = connection.getresponse()
        return response.status == 308 and response.getheader("Location") == ORIGIN + path
    except OSError:
        return False
    finally:
        connection.close()


def nginx_command(nginx, *arguments):
    # Do not expose diagnostics concerning certificates or unrelated NAS hosts.
    result = subprocess.run([nginx, *arguments], capture_output=True, timeout=20)
    require(result.returncode == 0, "nginx " + " ".join(arguments) + " fehlgeschlagen (Exit " + str(result.returncode) + ").")


def replace_include(content):
    handle, temporary = tempfile.mkstemp(prefix=".boerse-beta-redirect-", dir=str(PROFILE.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, INCLUDE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def protect_backup_directory(path, *, created):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0,
            "Das Backupverzeichnis muss ein root-eigenes Verzeichnis ohne Symlink sein.")
    if created:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            require((opened.st_dev, opened.st_ino, opened.st_uid) == (info.st_dev, info.st_ino, 0),
                    "Das neu angelegte Backupverzeichnis wurde zwischenzeitlich ersetzt.")
            # DSM ACL inheritance can expose mode 0777 despite mkdir(mode=0700).
            # Only correct the directory created by this invocation, through its checked descriptor.
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
            "Das Backupverzeichnis muss root gehören und Modus 0700 haben.")


def mutate(mode):
    descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        nginx, block = inspect_target()
        previous = INCLUDE.read_bytes() if INCLUDE.exists() else None
        if mode == "remove" and previous is None:
            print(json.dumps({"removed": False, "reason": "Keine verwaltete Begleitdatei vorhanden."}))
            return
        if mode == "apply" and previous == CONTENT and live_redirect():
            print(json.dumps({"installed": True, "changed": False, "origin": ORIGIN}))
            return
        nginx_command(nginx, "-t")
        try:
            BACKUPS.mkdir(mode=0o700, parents=True)
            created = True
        except FileExistsError:
            created = False
        protect_backup_directory(BACKUPS, created=created)
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=str(BACKUPS)))
        protect_backup_directory(backup, created=True)
        for name, content in (("beta-server-before.conf", block.encode()), ("include-before.conf", previous)):
            if content is not None:
                with os.fdopen(os.open(backup / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                    stream.write(content)
        metadata = {"origin": ORIGIN, "include_existed": previous is not None,
                    "beta_block_sha256": hashlib.sha256(block.encode()).hexdigest()}
        with os.fdopen(os.open(backup / "state.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(metadata, stream)
        changed = False
        reload_attempted = False
        def interrupted(signum, frame):
            raise RuntimeError("Unterbrochen; die Begleitdatei wird zurückgesetzt.")
        old_handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            changed = True
            if mode == "apply":
                replace_include(CONTENT)
            else:
                INCLUDE.unlink()
            inspect_target()
            nginx_command(nginx, "-t")
            reload_attempted = True
            nginx_command(nginx, "-s", "reload")
            if mode == "apply":
                for attempt in range(20):
                    if live_redirect():
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Der erwartete kanonische HTTP-308-Redirect ist nach Reload nicht aktiv.")
            changed = False
        except BaseException:
            if changed:
                if previous is None:
                    INCLUDE.unlink(missing_ok=True)
                else:
                    replace_include(previous)
                nginx_command(nginx, "-t")
                if reload_attempted:
                    nginx_command(nginx, "-s", "reload")
            raise
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
        print(json.dumps({"installed": mode == "apply", "changed": True, "origin": ORIGIN,
                          "backup": str(backup), "generated_vhost_unchanged": True}))


def main():
    parser = argparse.ArgumentParser(description="Nur den Beta-HTTP-Aufruf auf seinen kanonischen HTTPS-Origin umlenken.")
    parser.add_argument("mode", nargs="?", default="check", choices=("check", "apply", "remove"))
    args = parser.parse_args()
    if args.mode == "check":
        inspect_target()
        print(json.dumps({"preconditions_ok": True, "installed": INCLUDE.exists(),
                          "live_redirect": live_redirect(), "origin": ORIGIN,
                          "include": str(INCLUDE), "read_only": True}))
    else:
        mutate(args.mode)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
PY
