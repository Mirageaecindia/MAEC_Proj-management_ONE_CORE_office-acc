"""Corrections: an engineer moves hours logged on the wrong subtask; the target task's reviewer decides."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import models
from app.api.deps import get_correction_service
from app.core.security import get_current_user
from app.services.corrections import CorrectionService

router = APIRouter(tags=["corrections"])


class CorrectionIn(BaseModel):
    """Move `hours` of `work_date` from one of the engineer's subtasks to another on the same project."""

    work_date: date
    from_task_id: int
    to_task_id: int
    hours: float = Field(gt=0, le=24)
    note: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.get("/projects/{project_id}/hours-corrections")
def list_corrections(
    project_id: int,
    user: models.User = Depends(get_current_user),
    service: CorrectionService = Depends(get_correction_service),
):
    """Pending corrections first, then recent decisions; an engineer sees only their own."""
    return service.list(user, project_id)


@router.post("/projects/{project_id}/hours-corrections", status_code=201)
def propose_correction(
    project_id: int,
    payload: CorrectionIn,
    user: models.User = Depends(get_current_user),
    service: CorrectionService = Depends(get_correction_service),
):
    return service.propose(
        user, project_id, payload.work_date, payload.from_task_id, payload.to_task_id, payload.hours, payload.note
    )


@router.post("/hours-corrections/{correction_id}/approve")
def approve_correction(
    correction_id: int,
    user: models.User = Depends(get_current_user),
    service: CorrectionService = Depends(get_correction_service),
):
    return service.decide(user, correction_id, True, None, datetime.now(UTC))


@router.post("/hours-corrections/{correction_id}/reject")
def reject_correction(
    correction_id: int,
    payload: DecisionIn | None = None,
    user: models.User = Depends(get_current_user),
    service: CorrectionService = Depends(get_correction_service),
):
    return service.decide(user, correction_id, False, payload.reason if payload else None, datetime.now(UTC))


@router.post("/hours-corrections/{correction_id}/cancel")
def cancel_correction(
    correction_id: int,
    user: models.User = Depends(get_current_user),
    service: CorrectionService = Depends(get_correction_service),
):
    """The engineer withdraws their own pending correction."""
    return service.cancel(user, correction_id)
