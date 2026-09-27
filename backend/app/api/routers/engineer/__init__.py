"""Engineer endpoints (moving out of main.py feature by feature)."""

from fastapi import APIRouter

from app.api.routers.engineer import tracking

router = APIRouter()
router.include_router(tracking.router)
