from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.trade_journal import TradeJournalRepositoryUnavailable
from app.schemas import (
    TradeJournalAnalyticsResponse,
    TradeJournalCoverageResponse,
    TradeJournalDefaultsResponse,
    TradeJournalEntriesResponse,
    TradeJournalEntryRequest,
    TradeJournalEntryResponse,
    TradeJournalNoteRequest,
    TradeJournalTradeSummary,
    TradeJournalTradesResponse,
)
from app.services.trade_journal import (
    close_trade_journal_entry,
    create_trade_journal_entry,
    get_trade_journal_analytics,
    get_trade_journal_coverage,
    get_trade_journal_defaults,
    get_trade_journal_entries,
    get_trade_journal_entry,
    get_trade_journal_trade,
    get_trade_journal_trades,
    update_trade_journal_entry,
    update_trade_journal_notes,
)


router = APIRouter()


@router.get("", response_model=TradeJournalEntriesResponse)
def entries(
    ticker: str | None = Query(default=None, min_length=1, max_length=32),
    query: str | None = Query(default=None, max_length=120),
    entry_type: str | None = Query(default=None, pattern="^(buy|sell|ex_post)$"),
    position_status: str | None = Query(default=None, alias="status", pattern="^(open|closed|draft)$"),
    source: str | None = Query(default=None, pattern="^(broker|manual)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="newest", pattern="^(newest|oldest)$"),
) -> TradeJournalEntriesResponse:
    try:
        if not any((query, entry_type, position_status, source, date_from, date_to, offset)) and limit == 50 and sort == "newest":
            return get_trade_journal_entries(ticker)
        return get_trade_journal_entries(
            ticker,
            query=query,
            entry_type=entry_type,
            status=position_status,
            source=source,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
            sort=sort,
        )
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.get("/defaults", response_model=TradeJournalDefaultsResponse)
def defaults(
    ticker: str = Query(..., min_length=1, max_length=32),
    entry_type: str = Query(default="buy", pattern="^(buy|sell|ex_post)$"),
) -> TradeJournalDefaultsResponse:
    try:
        return get_trade_journal_defaults(ticker, entry_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.get("/trades", response_model=TradeJournalTradesResponse)
def trades(
    query: str | None = Query(default=None, max_length=120),
    date_from: date | None = None,
    date_to: date | None = None,
) -> TradeJournalTradesResponse:
    return get_trade_journal_trades(query=query, date_from=date_from, date_to=date_to)


@router.get("/trades/{trade_id}", response_model=TradeJournalTradeSummary)
def trade_detail(trade_id: str) -> TradeJournalTradeSummary:
    try:
        return get_trade_journal_trade(trade_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/analytics", response_model=TradeJournalAnalyticsResponse)
def analytics(
    query: str | None = Query(default=None, max_length=120),
    date_from: date | None = None,
    date_to: date | None = None,
) -> TradeJournalAnalyticsResponse:
    return get_trade_journal_analytics(query=query, date_from=date_from, date_to=date_to)


@router.get("/coverage", response_model=TradeJournalCoverageResponse)
def coverage() -> TradeJournalCoverageResponse:
    return get_trade_journal_coverage()


@router.post("", response_model=TradeJournalEntryResponse)
def create_entry(payload: TradeJournalEntryRequest) -> TradeJournalEntryResponse:
    try:
        return create_trade_journal_entry(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.get("/{entry_id}", response_model=TradeJournalEntryResponse)
def detail(entry_id: str) -> TradeJournalEntryResponse:
    try:
        return get_trade_journal_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.patch("/{entry_id}", response_model=TradeJournalEntryResponse)
def patch_entry(entry_id: str, payload: TradeJournalEntryRequest) -> TradeJournalEntryResponse:
    try:
        return update_trade_journal_entry(entry_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.patch("/{entry_id}/notes", response_model=TradeJournalEntryResponse)
def patch_notes(entry_id: str, payload: TradeJournalNoteRequest) -> TradeJournalEntryResponse:
    try:
        return update_trade_journal_notes(entry_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.post("/{entry_id}/close", response_model=TradeJournalEntryResponse)
def close_entry(entry_id: str) -> TradeJournalEntryResponse:
    try:
        return close_trade_journal_entry(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TradeJournalRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Handelstagebuch-Datenbank ist nicht erreichbar: {exc}",
        ) from exc
