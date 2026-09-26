"""Archived projects are read-only (TODO C1).

Enforced once, when the session flushes, so it covers every write path: the
Lead/Engineer endpoints in main.py, the BU Head services, and future code.
A flush that inserts, updates or deletes an archived project's data (or the
project row itself, except to unarchive it) is refused with 409.

Bulk `query.update()/delete()` statements skip flush events. The only bulk
writes on project data are the WBS node delete (behind the project-access
check, which hides archived projects from Leads) and the project delete
(which refuses archived projects itself).
"""

from sqlalchemy import event, select
from sqlalchemy.orm import Session

import models
from app.core.errors import ConflictError

ARCHIVED_READ_ONLY = "This project is archived and read-only."

_PROJECT_DATA = (
    models.WbsNode,
    models.WbsNodeHistory,
    models.GanttTask,
    models.TimeLogEntry,
    models.TimeSession,
    models.ResourceBooking,
    models.WeeklyHoursSubmission,
    models.ExtensionRequest,
    models.GovernanceAction,
)


def _refuse_writes_to_archived_projects(session: Session, _flush_context, _instances) -> None:
    touched, unarchiving = set(), set()
    for obj in (*session.new, *session.dirty, *session.deleted):
        if isinstance(obj, models.Project):
            if obj.id is not None:
                (touched if obj.archived_at is not None else unarchiving).add(obj.id)
        elif isinstance(obj, _PROJECT_DATA) and obj.project_id is not None:
            touched.add(obj.project_id)
    candidates = touched - unarchiving  # unarchiving a project may also write its audit entry
    if not candidates:
        return
    with session.no_autoflush:  # read the state before this flush
        archived = session.execute(
            select(models.Project.id).where(models.Project.id.in_(candidates), models.Project.archived_at.is_not(None))
        ).first()
    if archived:
        raise ConflictError(ARCHIVED_READ_ONLY)


def install() -> None:
    """Register the guard for every session (idempotent)."""
    if not event.contains(Session, "before_flush", _refuse_writes_to_archived_projects):
        event.listen(Session, "before_flush", _refuse_writes_to_archived_projects)
