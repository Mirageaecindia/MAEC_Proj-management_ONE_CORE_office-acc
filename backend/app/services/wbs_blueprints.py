"""Phase blueprints (decided 2026-10-07): the company's standard tasks for each of the five phases.

Each phase has one workbook in app/blueprints/ (one column: a bold row is a task, the rows
under it its subtasks). On WBS Structure the "+" of a phase card adds that phase's
blueprint to the project; a task or subtask that is already there is skipped, so a
blueprint can be added again after more were created by hand. The whole WBS workbook
upload stays for adding all five phases at once.
"""

from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

import models
from app.core.errors import NotFoundError
from app.services.access import require_project_lead
from app.services.wbs_outline import OutlineRow, add_rows, match_rows, parse_blueprint

BLUEPRINT_DIR = Path(__file__).resolve().parents[1] / "blueprints"

# URL key -> (phase, workbook)
BLUEPRINTS: dict[str, tuple[str, str]] = {
    "space-planning": ("Space Planning", "space_planning.xlsx"),
    "str-coordination": ("STR Coordination", "str_coordination.xlsx"),
    "id-coordination": ("ID Coordination", "id_coordination.xlsx"),
    "boh-area-rcp-coordination": ("BoH Area RCP Coordination", "boh_area_rcp_coordination.xlsx"),
    "submission": ("Submission", "submission.xlsx"),
}
UNKNOWN = "There is no blueprint for that phase."


@lru_cache(maxsize=len(BLUEPRINTS))
def blueprint_rows(key: str) -> tuple[OutlineRow, ...]:
    """The blueprint's tasks and subtasks, read once per process (the files ship with the app)."""
    if key not in BLUEPRINTS:
        raise NotFoundError(UNKNOWN)
    phase, filename = BLUEPRINTS[key]
    return tuple(parse_blueprint((BLUEPRINT_DIR / filename).read_bytes(), phase))


def catalog() -> list[dict]:
    """Each phase's blueprint and its size, for the confirmation before adding it."""
    out = []
    for key, (phase, _) in BLUEPRINTS.items():
        rows = blueprint_rows(key)
        tasks = sum(1 for row in rows if row.is_task)
        out.append({"key": key, "phase": phase, "tasks": tasks, "subtasks": len(rows) - tasks})
    return out


def _lead_project(db: Session, user: models.User, project_id: int) -> models.Project:
    project = db.get(models.Project, project_id)
    if project is None:
        raise NotFoundError("Project not found.")
    require_project_lead(db, user, project_id)
    return project


def preview(db: Session, user: models.User, project_id: int, key: str) -> dict:
    """How much of the phase's blueprint is already in the project, for the question before adding."""
    rows = list(blueprint_rows(key))
    _lead_project(db, user, project_id)
    nodes = db.query(models.WbsNode).filter_by(project_id=project_id).all()
    present = [row for row, match in zip(rows, match_rows(nodes, rows), strict=True) if match is not None]
    tasks = sum(1 for row in rows if row.is_task)
    present_tasks = sum(1 for row in present if row.is_task)
    return {
        "key": key,
        "phase": BLUEPRINTS[key][0],
        "tasks": tasks,
        "subtasks": len(rows) - tasks,
        "present_tasks": present_tasks,
        "present_subtasks": len(present) - present_tasks,
        "missing": len(rows) - len(present),
    }


def add_blueprint(db: Session, user: models.User, project_id: int, key: str, again: bool = False) -> dict:
    """Add the phase's blueprint to the project (the project's leads): the missing rows, or with
    `again` a full second copy at the bottom of the phase. Commits."""
    rows = blueprint_rows(key)
    project = _lead_project(db, user, project_id)
    result = add_rows(db, project, user, list(rows), again=again)
    db.commit()
    return {
        "phase": BLUEPRINTS[key][0],
        "created": result["created"],
        "skipped": result["updated"],
        "created_ids": result["created_ids"],
        "same_as": result["same_as"],
    }
