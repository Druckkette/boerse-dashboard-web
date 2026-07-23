from fastapi import APIRouter, HTTPException

from app.domain.sell.schemas import (
    ManualInputResponse,
    SellEvaluationRequest,
    SellEvaluationResponse,
    SellDiagnosticsResponse,
    SellManualInput,
    SellMetricsApiResponse,
    SellPostMortemNote,
    SellPostMortemNoteRequest,
    SellPostMortemNoteResponse,
    SellRankingResponse,
    SnoozeRequest,
    SnoozeResponse,
    TrancheLogEntry,
    TrancheLogResponse,
)
from app.domain.sell.service import (
    SellMarketDataUnavailableError,
    SellPositionNotFoundError,
    create_tranche_log_entry,
    evaluate_position_sell_decision,
    get_sell_diagnostics_for_position,
    get_sell_metrics_for_position,
    get_sell_post_mortem_notes,
    get_sell_position_ranking,
    snooze_sell_signal,
    update_manual_sell_inputs,
    upsert_sell_post_mortem_note,
)


router = APIRouter()


@router.get("/positions/ranking", response_model=SellRankingResponse)
def ranking() -> SellRankingResponse:
    return get_sell_position_ranking()


@router.get("/{ticker}/metrics", response_model=SellMetricsApiResponse)
def metrics(ticker: str) -> SellMetricsApiResponse:
    try:
        return get_sell_metrics_for_position(ticker)
    except SellPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SellMarketDataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{ticker}/evaluate", response_model=SellEvaluationResponse)
def evaluate(
    ticker: str,
    payload: SellEvaluationRequest | None = None,
) -> SellEvaluationResponse:
    try:
        return evaluate_position_sell_decision(ticker, payload)
    except SellPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SellMarketDataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{ticker}/diagnostics", response_model=SellDiagnosticsResponse)
def diagnostics(ticker: str) -> SellDiagnosticsResponse:
    try:
        return get_sell_diagnostics_for_position(ticker)
    except SellPositionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SellMarketDataUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{ticker}/post-mortem", response_model=list[SellPostMortemNote])
def post_mortem_notes(ticker: str) -> list[SellPostMortemNote]:
    return get_sell_post_mortem_notes(ticker)


@router.post("/{ticker}/post-mortem", response_model=SellPostMortemNoteResponse)
def save_post_mortem_note(
    ticker: str,
    payload: SellPostMortemNoteRequest,
) -> SellPostMortemNoteResponse:
    return upsert_sell_post_mortem_note(ticker, payload)


@router.patch("/{ticker}/manual", response_model=ManualInputResponse)
def update_manual(ticker: str, payload: SellManualInput) -> ManualInputResponse:
    return update_manual_sell_inputs(ticker, payload)


@router.post("/{ticker}/tranches", response_model=TrancheLogResponse)
def create_tranche(ticker: str, payload: TrancheLogEntry) -> TrancheLogResponse:
    return create_tranche_log_entry(ticker, payload)


@router.post("/{ticker}/snooze", response_model=SnoozeResponse)
def snooze(ticker: str, payload: SnoozeRequest) -> SnoozeResponse:
    return snooze_sell_signal(ticker, payload)
