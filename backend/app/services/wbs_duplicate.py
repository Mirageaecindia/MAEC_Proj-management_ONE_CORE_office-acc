"""Duplicating a WBS task or subtask (decided 2026-10-06).

The copy sits next to the original: a subtask's copy under the same task, a task's
copy as a new task with a copy of each of its subtasks. It keeps the name, phase,
lead, engineer, estimated hours and dates, and gets the next free WBS code at its
level ("1.4" -> "1.5"; task "3" -> "4", its subtasks "4.1", "4.2", ...), so codes stay
unique. It starts fresh: To Do, no hours, no comments, no history.

Who may duplicate: the project's lead, anything; an engineer, a subtask assigned
to them under a task assigned to them (what they may create anyway).
"""

from sqlalchemy.orm import Session

import models
from app.core.errors import ForbiddenError
from app.domain.wbs import TO_DO, child_prefix, next_code
from app.services.access import ENGINEER, LEAD

LEAD_ONLY = "Only the project's lead duplicates tasks."
NOT_YOURS = "You can only duplicate your own subtasks, under a task assigned to you."
READ_ONLY = "The WBS is read-only for your role on this project."

COPIED = (
    "task_name",
    "assigned_lead",
    "assigned_lead_user_id",
    "assigned_engineer_id",
    "estimated_hours",
    "description",
    "start_date",
    "target_due_date",
    "end_date",
    "phase",
)


def refusal(role: str, node: models.WbsNode, parent: models.WbsNode | None, user: models.User) -> str | None:
    """Why this user may not duplicate this node, or None when they may."""
    if role == LEAD:
        return None
    if role != ENGINEER:
        return READ_ONLY
    if parent is None:
        return LEAD_ONLY
    mine = user.employee_id is not None
    if not (mine and parent.assigned_engineer_id == user.employee_id == node.assigned_engineer_id):
        return NOT_YOURS
    return None


def duplicate_node(db: Session, node: models.WbsNode, role: str, user: models.User) -> models.WbsNode:
    """Copy a task (with its subtasks) or a subtask and return the copy. Commits."""
    parent = db.get(models.WbsNode, node.parent_id) if node.parent_id is not None else None
    reason = refusal(role, node, parent, user)
    if reason:
        raise ForbiddenError(reason)
    codes = [code for (code,) in db.query(models.WbsNode.wbs_code).filter_by(project_id=node.project_id)]

    if parent is not None:
        prefix = child_prefix(parent.wbs_code)
        copy = _copy(node, user, parent.id, next_code(prefix, codes) if prefix else None)
        db.add(copy)
    else:
        copy = _copy(node, user, None, next_code("", codes) if child_prefix(node.wbs_code) else None)
        db.add(copy)
        db.flush()  # the subtasks need the new task's id
        prefix = child_prefix(copy.wbs_code)
        subtasks = db.query(models.WbsNode).filter_by(parent_id=node.id).order_by(models.WbsNode.id)
        for number, subtask in enumerate(subtasks, start=1):
            db.add(_copy(subtask, user, copy.id, f"{prefix}{number}" if prefix else None))
    db.commit()
    db.refresh(copy)
    return copy


def _copy(node: models.WbsNode, user: models.User, parent_id: int | None, code: str | None) -> models.WbsNode:
    return models.WbsNode(
        project_id=node.project_id,
        parent_id=parent_id,
        wbs_code=code,
        created_by_user_id=user.id,
        deliverable_status=TO_DO,
        **{field: getattr(node, field) for field in COPIED},
    )
