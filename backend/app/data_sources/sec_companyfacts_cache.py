"""Persistent, atomically replaced SEC companyfacts bulk cache shared by workers."""
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
BULK_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
_zip_lock = Lock()


@lru_cache(maxsize=2)
def _opened_archive(path: str, modified_ns: int) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def cache_dir() -> Path:
    return Path(os.environ.get("BACKEND_CACHE_DIR", "/tmp/boerse-dashboard-cache")) / "sec_companyfacts"


def _paths() -> tuple[Path, Path]:
    root = cache_dir()
    return root / "companyfacts.zip", root / "metadata.json"


def bulk_status() -> dict:
    archive, metadata = _paths()
    try:
        result = json.loads(metadata.read_text())
        if archive.is_file() and zipfile.is_zipfile(archive):
            return {**result, "available": True, "bytes": archive.stat().st_size}
    except (OSError, ValueError, zipfile.BadZipFile):
        pass
    return {"available": archive.is_file() and zipfile.is_zipfile(archive)}


def refresh_companyfacts_bulk_cache(user_agent: str, *, max_age_hours: int = 24,
                                    min_members: int = 1000) -> dict:
    """One daily download per shared volume; a failed download keeps the old archive."""
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
            response = sec_get(BULK_URL, user_agent=user_agent, timeout=180, stream=True)
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
                member_count = sum(name.startswith("CIK") and name.endswith(".json") for name in data.namelist())
                if member_count < min_members:
                    raise ValueError(f"SEC-Bulk-Datei unvollständig ({member_count} Einträge)")
            size = temp_path.stat().st_size
            os.replace(temp_path, archive)
            temp_path = None
            result = {"fetched_at": datetime.now(UTC).isoformat(), "bytes": size,
                      "members": member_count, "available": True, "downloaded": True}
            with tempfile.NamedTemporaryFile(dir=archive.parent, mode="w", delete=False) as target:
                json.dump(result, target)
                metadata_temp = target.name
            os.replace(metadata_temp, metadata)
            record_provider_event("sec_bulk_downloads")
            logger.info("SEC companyfacts.zip aktualisiert: %s Bytes, %s CIKs", size, member_count)
            return result
        except Exception as exc:
            logger.warning("SEC-Bulk-Download fehlgeschlagen; alter Cache bleibt erhalten: %s", exc)
            return {**status, "downloaded": False, "error": str(exc)}
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def load_companyfacts(cik: str, user_agent: str, *, timeout: int = 15,
                      force_live: bool = False) -> tuple[dict, str]:
    """Use the local bulk first, then live SEC for new filings or cache misses."""
    archive, _ = _paths()
    member = f"CIK{cik}.json"
    cached: dict | None = None
    if archive.is_file():
        try:
            with _zip_lock:
                data = _opened_archive(str(archive), archive.stat().st_mtime_ns)
                cached = json.loads(data.read(member))
            record_provider_event("cache_hits")
        except (KeyError, OSError, ValueError, zipfile.BadZipFile):
            pass
    if cached is not None and not force_live:
        return cached, "sec_bulk_cache"
    try:
        response = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/{member}",
                           user_agent=user_agent, timeout=timeout)
        response.raise_for_status()
        return response.json(), "sec_companyfacts_live"
    except Exception as exc:
        if cached is not None:
            return cached, ("sec_bulk_cache_live_rate_limited" if getattr(exc, "reason_code", "") == "rate_limited"
                            else "sec_bulk_cache_live_provider_error")
        raise
