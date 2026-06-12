from __future__ import annotations

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import yahoo_symbol_diagnostics as yahoo_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_yahoo_symbol_diagnostics_worker_marks_job_done(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_diagnose(payload: dict, *, apply_mappings: bool = False) -> dict:
        assert apply_mappings is False
        return {
            "ok": True,
            "job_type": "yahoo_symbol_diagnostics",
            "requested_count": 1,
            "mapped_count": 0,
            "items": [{"source_ticker": "BRK-B", "best_candidate": "BRK.B", "status": "candidate_found"}],
        }

    monkeypatch.setattr(yahoo_module, "diagnose_yahoo_symbols", fake_diagnose)
    job = job_repository.create_job("yahoo_symbol_diagnostics", {"tickers": ["BRK-B"]})

    result = yahoo_module.yahoo_symbol_diagnostics.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert updated is not None
    assert updated.status == "done"
    assert updated.result["items"][0]["best_candidate"] == "BRK.B"


def test_yahoo_symbol_rescue_worker_marks_mapping_count(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_diagnose(payload: dict, *, apply_mappings: bool = False) -> dict:
        assert apply_mappings is True
        return {
            "ok": True,
            "job_type": "yahoo_symbol_rescue",
            "requested_count": 1,
            "mapped_count": 1,
            "items": [{"source_ticker": "BF-B", "best_candidate": "BF.B", "status": "candidate_found"}],
        }

    monkeypatch.setattr(yahoo_module, "diagnose_yahoo_symbols", fake_diagnose)
    job = job_repository.create_job("yahoo_symbol_rescue", {"tickers": ["BF-B"]})

    result = yahoo_module.yahoo_symbol_rescue.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["mapped_count"] == 1
    assert updated is not None
    assert updated.status == "done"
    assert "1 Mappings" in updated.message
