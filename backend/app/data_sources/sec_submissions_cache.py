"""Persistent SEC submissions bulk cache used for SIC/business classification."""
from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from threading import Lock

from app.data_sources.provider_usage import record_provider_event
from app.data_sources.sec_request import sec_get


logger = logging.getLogger(__name__)
BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
_zip_lock = Lock()


@lru_cache(maxsize=2)
def _opened_archive(path: str, modified_ns: int) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def cache_dir() -> Path:
    return Path(os.environ.get("BACKEND_CACHE_DIR", "/tmp/boerse-dashboard-cache")) / "sec_submissions"


def _paths() -> tuple[Path, Path]:
    root = cache_dir()
    return root / "submissions.zip", root / "metadata.json"


def bulk_status() -> dict:
    archive, metadata = _paths()
    try:
        result = json.loads(metadata.read_text())
        if archive.is_file() and zipfile.is_zipfile(archive):
            return {**result, "available": True, "bytes": archive.stat().st_size}
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    return {"available": archive.is_file() and zipfile.is_zipfile(archive)}


def refresh_submissions_bulk_cache(
    user_agent: str,
    *,
    max_age_hours: int = 24,
    min_members: int = 1000,
) -> dict:
    """Download the nightly SEC submissions archive atomically and reuse it for a day."""
    archive, metadata = _paths()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with (archive.parent / "download.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = bulk_status()
        try:
            fetched = datetime.fromisoformat(str(status.get("fetched_at", "")))
        except ValueError:
            fetched = datetime.min.replace(tzinfo=UTC)
        if status.get("available") and datetime.now(UTC) - fetched < timedelta(hours=max_age_hours):
            record_provider_event("cache_hits")
            return {**status, "downloaded": False}

        temp_path: Path | None = None
        try:
            response = sec_get(BULK_URL, user_agent=user_agent, timeout=240, stream=True)
            try:
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(dir=archive.parent, suffix=".zip", delete=False) as target:
                    temp_path = Path(target.name)
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            target.write(chunk)
            finally:
                response.close()

            with zipfile.ZipFile(temp_path) as data:
                member_count = sum(
                    name.startswith("CIK") and name.endswith(".json")
                    for name in data.namelist()
                )
                if member_count < min_members:
                    raise ValueError(f"SEC submissions bulk file incomplete ({member_count} entries)")

            size = temp_path.stat().st_size
            os.replace(temp_path, archive)
            temp_path = None
            result = {
                "fetched_at": datetime.now(UTC).isoformat(),
                "bytes": size,
                "members": member_count,
                "available": True,
                "downloaded": True,
            }
            with tempfile.NamedTemporaryFile(dir=archive.parent, mode="w", delete=False) as target:
                json.dump(result, target)
                metadata_temp = target.name
            os.replace(metadata_temp, metadata)
            record_provider_event("sec_bulk_downloads")
            logger.info("SEC submissions.zip updated: %s bytes, %s CIKs", size, member_count)
            return result
        except Exception as exc:
            logger.warning("SEC submissions bulk download failed; old cache retained: %s", exc)
            return {**status, "downloaded": False, "error": str(exc)}
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def load_submission(cik: str) -> dict | None:
    """Read one registrant submission document from the local bulk archive."""
    clean = str(cik or "").strip().zfill(10)
    if not clean.isdigit() or clean == "0000000000":
        return None
    archive, _ = _paths()
    if not archive.is_file():
        return None
    member = f"CIK{clean}.json"
    try:
        with _zip_lock:
            data = _opened_archive(str(archive), archive.stat().st_mtime_ns)
            payload = json.loads(data.read(member))
        record_provider_event("cache_hits")
        return payload if isinstance(payload, dict) else None
    except (KeyError, OSError, ValueError, zipfile.BadZipFile):
        return None
