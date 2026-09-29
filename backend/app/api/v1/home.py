from fastapi import APIRouter

from app.services.home import get_home_dashboard

router = APIRouter()


@router.get("")
def home_dashboard() -> dict:
    """Return the compact investor dashboard from persisted application data."""
    return get_home_dashboard()
