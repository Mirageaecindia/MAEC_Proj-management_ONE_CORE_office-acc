"""Rejected hours: a project's leads and the BU Head may approve them again within seven days."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import models
from app.api.deps import get_rejected_hours_service
from app.core.security import get_current_user
from app.services.rejected_hours import RejectedHours

router = APIRouter(tags=["rejected hours"])


class ReapproveIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)  # required; checked with the other rules
    attended_only: bool = False  # approve an unattended day only up to the engineer's last visit


@router.get("/projects/{project_id}/rejected-hours")
def list_rejected_hours(
    project_id: int,
    user: models.User = Depends(get_current_user),
    service: RejectedHours = Depends(get_rejected_hours_service),
):
    """Hours rejected on the project that can still be approved again, the nearest deadline first."""
    return service.list(user, project_id, datetime.now(UTC))


@router.post("/time-log-entries/{entry_id}/reapprove")
def reapprove_hours(
    entry_id: int,
    payload: ReapproveIn,
    user: models.User = Depends(get_current_user),
    service: RejectedHours = Depends(get_rejected_hours_service),
):
    return service.reapprove(user, entry_id, payload.reason, payload.attended_only, datetime.now(UTC))
