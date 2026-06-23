from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.trade_journal import TradeJournalRepositoryUnavailable
from app.schemas import (
    TradeJournalDefaultsResponse,
    TradeJournalEntriesResponse,
    TradeJournalEntryRequest,
    TradeJournalEntryResponse,
)
from app.services.trade_journal import (
    close_trade_journal_entry,
    create_trade_journal_entry,
    get_trade_journal_defaults,
    get_trade_journal_entries,
    get_trade_journal_entry,
    update_trade_journal_entry,
)


router = APIRouter()


@router.get("", response_model=TradeJournalEntriesResponse)
def entries(ticker: str | None = Query(default=None, min_length=1, max_length=32)) -> TradeJournalEntriesResponse:
    try:
        return get_trade_journal_entries(ticker)
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
