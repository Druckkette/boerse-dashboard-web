from fastapi import APIRouter

from app.repositories import settings as settings_repository
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import PushoverDeliveryLogItem, PushoverDeliveryLogResponse


router = APIRouter()


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
