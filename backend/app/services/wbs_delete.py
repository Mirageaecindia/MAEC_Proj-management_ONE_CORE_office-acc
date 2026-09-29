"""Deleting WBS tasks and subtasks, one or many at a time (decided 2026-09-29).

Who may delete: the project's lead deletes any task or subtask on the project;
an engineer deletes only subtasks under tasks assigned to them, never a task.
Deleting a task deletes its subtasks. A selection is deleted as a whole or
not at all: one refused item and nothing changes.

Hours already worked are never deleted or changed. An open Login session on a
deleted subtask is logged out and banked first, and the day rows keep the
subtask's name so the timesheet, the dashboards and the approval still show
them. Only the WBS items themselves go.
"""

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import case, func, update
from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.repositories.tracking import ACTIVE
from app.services.access import ENGINEER, LEAD
from app.services.tracking import end_session

LEAD_ONLY = "only the project's lead deletes tasks"
NOT_YOURS = "you can only delete subtasks under tasks assigned to you"
READ_ONLY = "The WBS is read-only for your role on this project."
NOTHING_SELECTED = "Select at least one task or subtask."
GONE = "Some of the selected items no longer exist. Refresh the page and try again."


@dataclass(frozen=True)
class Deleted:
    tasks: int
    subtasks: int
    hours_kept: float
    deleted_nodes: list[int]

    def as_dict(self) -> dict:
        return asdict(self)


def refusal(role: str, node: models.WbsNode, parent: models.WbsNode | None, user: models.User) -> str | None:
    """Why this user may not delete this node, or None when they may."""
    if role == LEAD:
        return None
    if role != ENGINEER:
        return READ_ONLY
    if node.parent_id is None:
        return LEAD_ONLY
    if parent is None or not user.employee_id or parent.assigned_engineer_id != user.employee_id:
        return NOT_YOURS
    return None


def delete_nodes(
    db: Session, project_id: int, role: str, user: models.User, node_ids: list[int], now: datetime
) -> Deleted:
    """Delete the selected nodes (and the subtasks of selected tasks) in a fixed
    number of queries, keeping every hour already worked. Commits."""
    ids = set(node_ids)
    if not ids:
        raise BadRequestError(NOTHING_SELECTED)
    node = models.WbsNode
    nodes = db.query(node).filter(node.id.in_(ids), node.project_id == project_id).all()
    if len(nodes) != len(ids):
        raise NotFoundError(GONE)
    parent_ids = {n.parent_id for n in nodes if n.parent_id is not None} - ids
    parents = {p.id: p for p in db.query(node).filter(node.id.in_(parent_ids))} if parent_ids else {}
    refused = [
        f"{n.wbs_code} {n.task_name}: {reason}"
        for n in nodes
        if (reason := refusal(role, n, parents.get(n.parent_id), user))
    ]
    if refused:
        raise ForbiddenError("Nothing was deleted. " + "; ".join(refused))

    children = db.query(node).filter(node.parent_id.in_(ids)).all()  # the tree is two levels deep
    doomed = {n.id: n for n in [*nodes, *children]}
    doomed_ids = list(doomed)
    subtasks = sum(1 for n in doomed.values() if n.parent_id is not None)

    session = models.TimeSession
    on_doomed = session.subtask_id.in_(doomed_ids) | session.task_id.in_(doomed_ids)
    for open_session in db.query(session).filter(on_doomed, session.status == ACTIVE):
        end_session(db, open_session, now)  # the time worked until now is banked, not lost
    db.flush()

    entry = models.TimeLogEntry
    hours_kept = db.query(func.sum(entry.hours)).filter(entry.task_id.in_(doomed_ids)).scalar() or 0
    db.execute(
        update(entry)
        .where(entry.task_id.in_(doomed_ids))
        .values(task_name=case({id_: n.task_name for id_, n in doomed.items()}, value=entry.task_id))
    )
    db.query(models.WbsNodeHistory).filter(models.WbsNodeHistory.node_id.in_(doomed_ids)).delete(
        synchronize_session=False
    )
    db.query(session).filter(on_doomed).delete(synchronize_session=False)
    db.query(node).filter(node.id.in_(doomed_ids)).delete(synchronize_session=False)
    db.commit()
    return Deleted(len(doomed) - subtasks, subtasks, round(float(hours_kept), 2), doomed_ids)
