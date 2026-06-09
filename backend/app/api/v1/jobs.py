from fastapi import APIRouter, HTTPException, Query, status

from app.schemas import (
    JobCancelResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobDetailResponse,
    JobListResponse,
)
from app.services.jobs import JobConflictError, cancel_job, get_job, list_jobs, start_job


router = APIRouter()


@router.get("", response_model=JobListResponse)
def list_job_runs(limit: int = Query(default=50, ge=1, le=200)) -> JobListResponse:
    return JobListResponse(jobs=list_jobs(limit=limit))


@router.get("/{job_id}", response_model=JobDetailResponse)
def job_detail(job_id: str) -> JobDetailResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetailResponse(job=job)


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
