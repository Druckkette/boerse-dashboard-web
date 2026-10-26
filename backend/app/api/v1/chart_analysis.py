from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.domain.chart_patterns import PatternParameters
from app.repositories.prices import PriceRepositoryUnavailable
from app.repositories.settings import SettingsRepositoryUnavailable
from app.services import chart_analysis as service
from app.services.jobs import JobConflictError, start_job
from app.schemas import JobCreateRequest


router = APIRouter()


def _call(operation):
    try:
        return operation()
    except (SettingsRepositoryUnavailable, PriceRepositoryUnavailable) as exc:
        raise HTTPException(
            status_code=503,
            detail="Chartanalyse: Datenbank nicht erreichbar. Bitte erneut versuchen.",
        ) from exc


@router.get("/config")
def config():
    return _call(service.get_config)


@router.put("/config")
def update_config(payload: PatternParameters):
    return _call(lambda: service.save_config(payload))


@router.get("/results")
def results(
    kind: str | None = Query(
        None, pattern="^(cup_with_handle|cup_without_handle|double_bottom|high_tight_flag|box)$"
    ),
    status: str | None = Query(
        None, pattern="^(ready|breakout|unconfirmed_breakout|invalidated|expired)$"
    ),
    search: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return _call(
        lambda: service.get_results(
            kind=kind, status=status, search=search, offset=offset, limit=limit
        )
    )


@router.post("/scan", status_code=202)
def scan():
    try:
        return {"job": start_job(JobCreateRequest(type="scan_chart_patterns", payload={}))}
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{ticker}")
def chart(ticker: str, as_of: date | None = None):
    import re

    clean = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.=_^\-]{0,31}", clean):
        raise HTTPException(status_code=422, detail="Ungültiger Ticker.")
    return _call(lambda: service.analyse(clean, as_of=as_of))
