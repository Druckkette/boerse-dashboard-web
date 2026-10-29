from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

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
    RuntimeEnvUnavailable,
    get_database_target,
    get_app_settings,
    get_data_diagnostics,
    get_data_quality_summary,
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


@router.get("/data-quality-summary")
def read_data_quality_summary() -> dict:
    return get_data_quality_summary()


@router.patch("", response_model=AppSettings)
def patch_settings(payload: SettingsPatch) -> AppSettings:
    from app.repositories.settings import SettingsRepositoryUnavailable
    try:
        return update_app_settings(payload)
    except SettingsRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Einstellungen konnten nicht gespeichert werden. Der Entwurf bleibt erhalten.") from exc
    except ValidationError as exc:
        messages = [error["msg"].removeprefix("Value error, ") for error in exc.errors()]
        raise HTTPException(status_code=422, detail=" ".join(messages[:3])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
def read_runtime_config() -> RuntimeConfigResponse:
    return get_runtime_config()


@router.patch("/runtime-config", response_model=RuntimeConfigResponse)
def patch_runtime_config(payload: RuntimeConfigPatch) -> RuntimeConfigResponse:
    from app.repositories.settings import SettingsRepositoryUnavailable
    try:
        return update_runtime_config(payload)
    except SettingsRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Konfiguration konnte nicht gespeichert werden. Der Entwurf bleibt erhalten.") from exc
    except RuntimeEnvUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/runtime-config/test", response_model=RuntimeConfigTestResponse)
def test_runtime_config_value(payload: RuntimeConfigTestRequest) -> RuntimeConfigTestResponse:
    return test_runtime_config(payload)


@router.get("/database-target", response_model=DatabaseTargetResponse)
def read_database_target() -> DatabaseTargetResponse:
    return get_database_target()


@router.post("/database-target", response_model=DatabaseTargetResponse)
def switch_database_target_value(payload: DatabaseTargetSwitchRequest) -> DatabaseTargetResponse:
    from app.repositories.settings import SettingsRepositoryUnavailable
    try:
        return switch_database_target(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (SettingsRepositoryUnavailable, RuntimeEnvUnavailable) as exc:
        raise HTTPException(status_code=503, detail="Datenbankziel nicht vollständig gespeichert. Dienste nicht neu starten; Konfiguration erneut speichern.") from exc


@router.post("/runtime-services/restart", response_model=RuntimeServicesRestartResponse)
def restart_runtime_services_value() -> RuntimeServicesRestartResponse:
    return restart_runtime_services()
