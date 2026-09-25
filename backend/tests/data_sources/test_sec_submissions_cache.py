from __future__ import annotations

import json
import zipfile

from app.data_sources import sec_submissions_cache


def _write_archive(tmp_path, member: str) -> None:
    root = tmp_path / "sec_submissions"
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(root / "submissions.zip", "w") as archive:
        archive.writestr(
            member,
            json.dumps(
                {
                    "cik": "789019",
                    "sic": "7372",
                    "sicDescription": "Services-Prepackaged Software",
                }
            ),
        )


def test_load_submission_from_root_member(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BACKEND_CACHE_DIR", str(tmp_path))
    sec_submissions_cache._opened_archive.cache_clear()
    _write_archive(tmp_path, "CIK0000789019.json")

    payload = sec_submissions_cache.load_submission("789019")

    assert payload is not None
    assert payload["sic"] == "7372"


def test_load_submission_from_nested_member(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BACKEND_CACHE_DIR", str(tmp_path))
    sec_submissions_cache._opened_archive.cache_clear()
    _write_archive(tmp_path, "submissions/CIK0000789019.json")

    payload = sec_submissions_cache.load_submission("0000789019")

    assert payload is not None
    assert payload["sicDescription"] == "Services-Prepackaged Software"
