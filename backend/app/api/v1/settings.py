from fastapi import APIRouter

from app.schemas import AppSettings, DataDiagnosticsResponse, SettingsPatch
from app.services.settings import get_app_settings, get_data_diagnostics, update_app_settings


router = APIRouter()


@router.get("", response_model=AppSettings)
def read_settings() -> AppSettings:
    return get_app_settings()


@router.get("/data-diagnostics", response_model=DataDiagnosticsResponse)
def read_data_diagnostics() -> DataDiagnosticsResponse:
    return get_data_diagnostics()


@router.patch("", response_model=AppSettings)
def patch_settings(payload: SettingsPatch) -> AppSettings:
    return update_app_settings(payload)
