from fastapi import APIRouter, HTTPException
import re

from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import PushoverDeliveryLogItem, PushoverDeliveryLogResponse


router = APIRouter()


@router.get("/research")
def research() -> dict:
    from app.services.research_results import research_results
    try:
        return research_results()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Verifizierte Forschungsergebnisse derzeit nicht verfügbar.") from exc


@router.get("/notifications", response_model=PushoverDeliveryLogResponse)
def notifications() -> PushoverDeliveryLogResponse:
    try:
        rows = settings_repository.read_pushover_delivery_log()
    except SettingsRepositoryUnavailable:
        rows = []
    entries: list[PushoverDeliveryLogItem] = []
    for row in rows:
        try:
            entries.append(PushoverDeliveryLogItem.model_validate(row))
        except ValueError:
            continue
    return PushoverDeliveryLogResponse(entries=entries)


def _notification_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,31}", ticker):
        raise HTTPException(status_code=422, detail="Bitte ein gültiges Aktiensymbol auswählen.")
    return ticker


@router.post("/notifications/stops/{ticker}/rearm")
def rearm_stop_notifications(ticker: str) -> dict:
    from app.services.stop_alerts import rearm_stop_alerts
    try:
        return rearm_stop_alerts(_notification_ticker(ticker))
    except SettingsRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Stoppalarm konnte nicht erneut freigegeben werden.") from exc


@router.post("/notifications/atr/{ticker}/rearm")
def rearm_atr_notifications(ticker: str) -> dict:
    try:
        return settings_repository.request_atr_rearm(_notification_ticker(ticker))
    except SettingsRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="ATR-Alarm konnte nicht erneut freigegeben werden.") from exc
