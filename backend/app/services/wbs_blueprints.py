"""WBS node blueprints: each node's standard tasks, added to a project with its "+" (decided 2026-10-07).

The nodes are the sheets of the stage workbooks in app/blueprints/ (CD, SD, DD; since
2026-10-15, app/domain/wbs_nodes.py), each sheet taken as it is (wbs_outline.parse_node_sheet).
On WBS Structure the "+" of a node card adds that node's tasks to the project; a task or
subtask that is already there is skipped, so a blueprint can be added again after more were
created by hand. The page shows a card, and lets a lead add tasks, only for the nodes listed here.

The five original phases (Space Planning ... Submission) are no longer offered; tasks already
filed under them stay on their projects and keep working.
"""

from functools import cache

from sqlalchemy.orm import Session

import models
from app.core.errors import NotFoundError
from app.domain.wbs_nodes import BLUEPRINT_DIR, NodeSheet, node_sheets
from app.services.access import require_project_lead
from app.services.wbs_outline import OutlineRow, add_rows, match_rows, parse_node_sheet

# URL key -> the node's sheet, stage by stage in sheet order.
BLUEPRINTS: dict[str, NodeSheet] = {node.key: node for node in node_sheets()}
UNKNOWN = "There is no blueprint for that node."


@cache
def blueprint_rows(key: str) -> tuple[OutlineRow, ...]:
    """The node's tasks and subtasks, read once per process (the files ship with the app)."""
    if key not in BLUEPRINTS:
        raise NotFoundError(UNKNOWN)
    node = BLUEPRINTS[key]
    return tuple(parse_node_sheet((BLUEPRINT_DIR / node.workbook).read_bytes(), node.phase, node.sheet))


def catalog() -> list[dict]:
    """Each node's blueprint and its size, for the cards and the confirmation before adding it."""
    out = []
    for key, node in BLUEPRINTS.items():
        rows = blueprint_rows(key)
        tasks = sum(1 for row in rows if row.is_task)
        out.append(
            {"key": key, "phase": node.phase, "stage": node.stage, "tasks": tasks, "subtasks": len(rows) - tasks}
        )
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
        "phase": BLUEPRINTS[key].phase,
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
        "phase": BLUEPRINTS[key].phase,
        "created": result["created"],
        "skipped": result["updated"],
        "created_ids": result["created_ids"],
        "same_as": result["same_as"],
    }
