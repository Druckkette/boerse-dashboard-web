from fastapi import APIRouter

from app.schemas import AppSettings, DataDiagnosticsResponse, RuntimeConfigPatch, RuntimeConfigResponse, SettingsPatch
from app.services.settings import (
    get_app_settings,
    get_data_diagnostics,
    get_runtime_config,
    update_app_settings,
    update_runtime_config,
)


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


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
def read_runtime_config() -> RuntimeConfigResponse:
    return get_runtime_config()


@router.patch("/runtime-config", response_model=RuntimeConfigResponse)
def patch_runtime_config(payload: RuntimeConfigPatch) -> RuntimeConfigResponse:
    return update_runtime_config(payload)
