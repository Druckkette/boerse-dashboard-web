"""Explicit shared frontend/backend policy. Browser-supplied roles are never trusted."""
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl

_policy = Path(__file__).with_name("beta_api_policy.json")
if not _policy.exists():
    _policy = Path(__file__).resolve().parents[2] / "frontend/src/lib/beta/api-policy.json"
RULES = json.loads(_policy.read_text())
TICKER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9.=_^-]{0,31}"


def beta_api_allowed(method: str, path: str, query: str = "") -> bool:
    if any(char in path for char in ("%", "\\", "..")) or len(query) > 2048:
        return False
    for rule in RULES:
        pattern = rule["path"].replace("{ticker}", TICKER_PATTERN).replace(
            "{group}", r"[A-Za-z0-9_-]{1,80}"
        ).replace("{job}", r"beta_[a-f0-9]{32}")
        if method == rule["method"] and re.fullmatch(pattern, path) and path not in rule.get("exclude", []):
            params = parse_qsl(query, keep_blank_values=True)
            return len(params) <= 32 and all(
                key in rule["query"] and len(value) <= 400 for key, value in params
            )
    return False


def public_projection(value):
    # Audited models already project stock/market fields. Remove operational data from
    # prepared dict summaries; never return persisted job IDs or arbitrary source metadata.
    hidden = {"source_job_id", "job_id", "component_errors", "errors", "metadata",
              "metadata_json", "payload", "error_message", "missing_tickers", "_screening"}
    if isinstance(value, dict):
        return {key: public_projection(item) for key, item in value.items() if key not in hidden}
    if isinstance(value, list):
        return [public_projection(item) for item in value]
    return value
