"""Subtask Login/Logout: the only source of an engineer's working hours."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import models
from app.api.deps import get_tracking_service
from app.core.security import require_staff
from app.services.tracking import TrackingService

router = APIRouter(prefix="/subtask-tracking", tags=["tracking"])


class TrackingStart(BaseModel):
    subtask_id: int


class Heartbeat(BaseModel):
    last_active_at: datetime | None = None  # the engineer's last click, key press or switch to the app's tab


@router.post("/heartbeat")
def heartbeat(
    payload: Heartbeat | None = None,
    user: models.User = Depends(require_staff),
    service: TrackingService = Depends(get_tracking_service),
):
    """Sent every minute by each open tab. Returns the subtask the engineer is logged in to, if any,
    whether the day is past the 8-hour mark, and a logout the system did for want of a visit."""
    return service.heartbeat(user, payload.last_active_at if payload else None)


@router.post("/start", status_code=201)
def start(
    payload: TrackingStart,
    user: models.User = Depends(require_staff),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.start(user, payload.subtask_id)


@router.post("/logout")
def logout(
    user: models.User = Depends(require_staff),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.logout(user)
