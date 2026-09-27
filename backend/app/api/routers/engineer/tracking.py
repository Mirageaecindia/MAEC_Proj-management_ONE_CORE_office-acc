"""Subtask Login/Logout: the only source of an engineer's working hours."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import models
from app.api.deps import get_tracking_service
from app.core.security import require_engineer
from app.services.tracking import TrackingService

router = APIRouter(prefix="/subtask-tracking", tags=["tracking"])


class TrackingStart(BaseModel):
    subtask_id: int


@router.post("/heartbeat")
def heartbeat(
    user: models.User = Depends(require_engineer),
    service: TrackingService = Depends(get_tracking_service),
):
    """Sent every minute by each open tab. Returns the subtask the engineer is logged in to, if any."""
    return service.heartbeat(user)


@router.post("/start", status_code=201)
def start(
    payload: TrackingStart,
    user: models.User = Depends(require_engineer),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.start(user, payload.subtask_id)


@router.post("/logout")
def logout(
    user: models.User = Depends(require_engineer),
    service: TrackingService = Depends(get_tracking_service),
):
    return service.logout(user)
