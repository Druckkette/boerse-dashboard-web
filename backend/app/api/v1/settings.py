from fastapi import APIRouter

from app.schemas import AppSettings, SettingsPatch
from app.services.settings import get_app_settings, update_app_settings


router = APIRouter()


@router.get("", response_model=AppSettings)
def read_settings() -> AppSettings:
    return get_app_settings()


@router.patch("", response_model=AppSettings)
def patch_settings(payload: SettingsPatch) -> AppSettings:
    return update_app_settings(payload)
