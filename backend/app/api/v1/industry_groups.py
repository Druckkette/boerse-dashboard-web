from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.repositories import industry_groups as repository
from app.services.industry_groups import TAXONOMY_VERSION, audit_csv, review_queue, set_manual_override
from app.services import industry_group_rs


router = APIRouter()


class ManualOverrideRequest(BaseModel):
    ticker: str
    industry_group_id: str
    reason: str = ""


@router.get("/diagnostics")
def diagnostics() -> dict:
    return repository.diagnostics(TAXONOMY_VERSION)


@router.get("/review")
def needs_review(limit: int = Query(default=500, ge=1, le=5000)) -> dict:
    rows = review_queue(limit=limit)
    return {"taxonomy_version": TAXONOMY_VERSION, "count": len(rows), "items": rows}


@router.post("/manual-override")
def manual_override(payload: ManualOverrideRequest) -> dict:
    try:
        set_manual_override(
            ticker=payload.ticker,
            group_id=payload.industry_group_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "ticker": payload.ticker.strip().upper(), "taxonomy_version": TAXONOMY_VERSION}


@router.get("/audit.csv")
def export_audit_csv() -> Response:
    return Response(
        content=audit_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="industry-group-classification.csv"'},
    )



@router.get("/rs/rankings")
def rs_rankings(
    sector: str = Query(default=""),
    industry_family: str = Query(default=""),
    include_small: bool = Query(default=True),
) -> dict:
    return industry_group_rs.list_rankings(
        sector=sector,
        industry_family=industry_family,
        include_small=include_small,
    )


@router.get("/rs/diagnostics")
def rs_diagnostics() -> dict:
    return industry_group_rs.diagnostics()


@router.get("/rs/{group_code}")
def rs_group_detail(group_code: str) -> dict:
    result = industry_group_rs.group_detail(group_code)
    if result is None:
        raise HTTPException(status_code=404, detail="Industry Group RS not found")
    return result


@router.get("/rs/{group_code}/members")
def rs_group_members(group_code: str) -> dict:
    result = industry_group_rs.group_detail(group_code)
    if result is None:
        raise HTTPException(status_code=404, detail="Industry Group RS not found")
    return {
        "group": result["group"],
        "members": result["members"],
        "top_stocks": result["top_stocks"],
    }


@router.get("/stock-context/{ticker}")
def stock_industry_group_context(ticker: str) -> dict:
    result = industry_group_rs.stock_group_context(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail="Industry Group membership not found")
    return result
