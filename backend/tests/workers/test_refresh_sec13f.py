from __future__ import annotations

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import refresh_sec13f as refresh_sec13f_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_refresh_sec13f_runs_real_sec_path_without_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_payloads: list[dict] = []

    def fake_refresh(payload: dict, *, progress_callback):
        seen_payloads.append(payload)
        progress_callback(40, "SEC Test", "synthetische SEC-Daten", {"records_seen": 1})
        return {
            "ok": True,
            "source": "sec",
            "records_seen": 1,
            "records_written": 1,
            "metadata": {"current_period": "2025-12-31"},
        }

    monkeypatch.setattr(refresh_sec13f_module, "refresh_institutional_13f_from_sec", fake_refresh)
    payload = {"mode": "manual", "tickers": ["NVDA"]}
    job = job_repository.create_job("refresh_sec13f", payload)

    result = refresh_sec13f_module.refresh_sec13f.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert seen_payloads == [payload]
    assert result["ok"] is True
    assert result["source"] == "sec"
    assert result["records_written"] == 1
    assert updated is not None
    assert updated.status == "done"


def test_refresh_sec13f_still_accepts_legacy_streamlit_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_ingest(payload: dict) -> dict:
        assert payload["tickers"]["NVDA"]["period"] == "2025-12-31"
        return {"ok": True, "source": "payload", "records_seen": 1, "records_written": 1}

    monkeypatch.setattr(refresh_sec13f_module, "ingest_institutional_13f_payload", fake_ingest)
    payload = {
        "metadata": {"source_url": "legacy"},
        "tickers": {
            "NVDA": {
                "period": "2025-12-31",
                "holder_count": 12,
            }
        },
    }
    job = job_repository.create_job("refresh_sec13f", payload)

    result = refresh_sec13f_module.refresh_sec13f.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["source"] == "payload"
    assert updated is not None
    assert updated.status == "done"
