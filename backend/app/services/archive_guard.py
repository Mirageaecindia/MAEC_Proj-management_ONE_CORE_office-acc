"""Archived projects are read-only (TODO C1).

Enforced once, when the session flushes, so it covers every write path: the
Lead/Engineer endpoints in main.py, the BU Head services, and future code.
A flush that inserts, updates or deletes an archived project's data (or the
project row itself) is refused with 409. Notifications are not project data,
so they can still be marked read.

The one exemption is explicit: archiving and unarchiving run inside
`lifecycle_writes`, because they write to the project themselves (archived_at,
the audit entry, ended tracking sessions, a cancelled extension request).

Bulk `query.update()/delete()` statements skip flush events. The only bulk
writes on project data are the WBS node delete (behind the project-access
check, which hides archived projects from Leads) and the project delete
(which refuses archived projects itself).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import Session

import models
from app.core.errors import ConflictError

ARCHIVED_READ_ONLY = "This project is archived and read-only."
_LIFECYCLE_KEY = "archive_guard.lifecycle_project_ids"  # in Session.info

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


@contextmanager
def lifecycle_writes(session: Session, project_id: int) -> Iterator[None]:
    """Allow the archive/unarchive operation to write to this project, whatever its state."""
    allowed = session.info.setdefault(_LIFECYCLE_KEY, set())
    allowed.add(project_id)
    try:
        yield
    finally:
        allowed.discard(project_id)


def _refuse_writes_to_archived_projects(session: Session, _flush_context, _instances) -> None:
    touched = set()
    for obj in (*session.new, *session.dirty, *session.deleted):
        if isinstance(obj, models.Project):
            if obj.id is not None:
                touched.add(obj.id)
        elif isinstance(obj, _PROJECT_DATA) and obj.project_id is not None:
            touched.add(obj.project_id)
    candidates = touched - session.info.get(_LIFECYCLE_KEY, set())
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
