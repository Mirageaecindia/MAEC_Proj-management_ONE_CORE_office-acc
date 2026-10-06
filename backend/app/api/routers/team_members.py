"""A lead's team on a project: the people Assign Engineer offers (app/services/team_members.py)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import models
from app.api.deps import get_team_members_service
from app.core.security import get_current_user
from app.services.team_members import TeamMembers

router = APIRouter(tags=["team members"])


class TeamIn(BaseModel):
    employee_ids: list[int] = Field(default_factory=list, max_length=2000)


@router.get("/projects/{project_id}/team-members")
def list_team_members(
    project_id: int,
    user: models.User = Depends(get_current_user),
    service: TeamMembers = Depends(get_team_members_service),
) -> dict:
    return {"employee_ids": service.list(user, project_id)}


@router.put("/projects/{project_id}/team-members")
def replace_team_members(
    project_id: int,
    payload: TeamIn,
    user: models.User = Depends(get_current_user),
    service: TeamMembers = Depends(get_team_members_service),
) -> dict:
    return {"employee_ids": service.replace(user, project_id, payload.employee_ids)}
