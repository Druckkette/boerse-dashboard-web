from fastapi import APIRouter

from app.schemas import AppSettings, SettingsPatch
from app.services.dummy_data import get_settings_dummy, update_settings_dummy


router = APIRouter()


@router.get("", response_model=AppSettings)
def read_settings() -> AppSettings:
    return get_settings_dummy()


@router.patch("", response_model=AppSettings)
def patch_settings(payload: SettingsPatch) -> AppSettings:
    return update_settings_dummy(payload)

