from fastapi import APIRouter, HTTPException

from app.schemas import (
    AppSettings,
    DataDiagnosticsResponse,
    DatabaseTargetResponse,
    DatabaseTargetSwitchRequest,
    RuntimeConfigPatch,
    RuntimeConfigResponse,
    RuntimeConfigTestRequest,
    RuntimeConfigTestResponse,
    RuntimeServicesRestartResponse,
    SettingsPatch,
)
from app.services.settings import (
    get_database_target,
    get_app_settings,
    get_data_diagnostics,
    get_runtime_config,
    restart_runtime_services,
    switch_database_target,
    test_runtime_config,
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


@router.post("/runtime-config/test", response_model=RuntimeConfigTestResponse)
def test_runtime_config_value(payload: RuntimeConfigTestRequest) -> RuntimeConfigTestResponse:
    return test_runtime_config(payload)


@router.get("/database-target", response_model=DatabaseTargetResponse)
def read_database_target() -> DatabaseTargetResponse:
    return get_database_target()


@router.post("/database-target", response_model=DatabaseTargetResponse)
def switch_database_target_value(payload: DatabaseTargetSwitchRequest) -> DatabaseTargetResponse:
    try:
        return switch_database_target(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runtime-services/restart", response_model=RuntimeServicesRestartResponse)
def restart_runtime_services_value() -> RuntimeServicesRestartResponse:
    return restart_runtime_services()
