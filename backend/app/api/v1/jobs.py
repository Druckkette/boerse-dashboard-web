from fastapi import APIRouter, HTTPException, Query, status

from app.schemas import (
    JobCancelResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
    JobListResponse,
)
from app.services.jobs import JobConflictError, _job_list_summary, cancel_job, get_job, list_jobs, start_job
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from app.repositories import refresh_work
from app.data_sources.provider_usage import usage_today
from app.data_sources.sec_companyfacts_cache import bulk_status


router = APIRouter()


@router.get("", response_model=JobListResponse)
def list_job_runs(limit: int = Query(default=50, ge=1, le=200)) -> JobListResponse:
    return JobListResponse(jobs=list_jobs(limit=limit))


class ReportWorkGroup(BaseModel):
    group: str
    status: str
    reason_code: str = ""
    count: int
    due_count: int = 0
    next_due_at: datetime | None = None


class ReportWorkActive(BaseModel):
    ticker: str
    group: str
    lease_until: datetime | None = None


class ReportWorkStatus(BaseModel):
    due_count: int
    oldest_due_at: datetime | None = None
    next_due_at: datetime | None = None
    groups: list[ReportWorkGroup]
    active: list[ReportWorkActive]
    provider_usage: dict[str, int] = {}
    sec_bulk_cache: dict = {}


@router.get("/report-work", response_model=ReportWorkStatus)
def report_work_status() -> ReportWorkStatus:
    try:
        return ReportWorkStatus.model_validate({**refresh_work.summary(),
                                                 "provider_usage": usage_today(),
                                                 "sec_bulk_cache": bulk_status()})
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Berichtswarteschlange nicht erreichbar. Migration und Datenbank pruefen.") from exc


@router.get("/{job_id}", response_model=JobDetailResponse)
def job_detail(job_id: str, compact: bool = False) -> JobDetailResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetailResponse(job=_job_list_summary(job) if compact else job)


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: JobCreateRequest) -> JobCreateResponse:
    try:
        job = start_job(payload)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobCreateResponse(job=job)


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_job_run(job_id: str) -> JobCancelResponse:
    job, cancelled = cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobCancelResponse(job=job, cancelled=cancelled)
