from fastapi import APIRouter

from app.schemas import SetupStatusResponse
from app.services.setup import get_setup_status


router = APIRouter()


@router.get("/status", response_model=SetupStatusResponse)
def read_setup_status() -> SetupStatusResponse:
    return get_setup_status()
