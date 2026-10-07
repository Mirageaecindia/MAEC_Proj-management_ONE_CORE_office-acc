"""Phase blueprints: the standard tasks of each phase, added to a project (app/services/wbs_blueprints.py)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from app.core.database import get_db
from app.core.security import get_current_user
from app.services import wbs_blueprints

router = APIRouter(tags=["wbs blueprints"])


@router.get("/wbs-blueprints")
def list_blueprints(_user: models.User = Depends(get_current_user)) -> list[dict]:
    """The five phases' blueprints with their number of tasks and subtasks."""
    return wbs_blueprints.catalog()


@router.post("/projects/{project_id}/wbs-blueprints/{phase}")
def add_blueprint(
    project_id: int,
    phase: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Add a phase's blueprint to the project; what is already there is skipped (project leads)."""
    return wbs_blueprints.add_blueprint(db, user, project_id, phase)
