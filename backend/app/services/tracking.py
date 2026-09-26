"""Automatic subtask time tracking: banking tracked seconds into timesheets.

Shared by the Engineer tracking endpoints in main.py (Logout) and project
archiving (which ends any active sessions).
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

import models
from app.core.security import as_utc
from app.domain.timesheets import PENDING_REVIEW

ACTIVE, ENDED = "active", "ended"


def upsert_subtask_time_log(
    db: Session, project_id: int, task_id: int, employee_id: int, day: date, seconds: int
) -> models.TimeLogEntry | None:
    """Fold tracked seconds into the weekly time-log row (project x subtask x
    engineer x week) that the Lead approves, so tracked and manual hours stay
    in one place. Every day of the week is banked; approval decides what stands."""
    hours = round(seconds / 3600, 2)
    if hours <= 0:
        return None
    week_start = day - timedelta(days=day.weekday())
    field = models.DAY_FIELDS[day.weekday()]
    entry = (
        db.query(models.TimeLogEntry)
        .filter_by(project_id=project_id, task_id=task_id, employee_id=employee_id, week_start_date=week_start)
        .first()
    )
    if entry is None:
        entry = models.TimeLogEntry(
            project_id=project_id,
            task_id=task_id,
            employee_id=employee_id,
            week_start_date=week_start,
            approval_status=PENDING_REVIEW,
        )
        db.add(entry)
    setattr(entry, field, round((getattr(entry, field) or 0) + hours, 2))
    return entry


def end_session(db: Session, session: models.TimeSession, now: datetime) -> None:
    """End a session with the time it has already synced (capped when synced),
    banked on the day it started. The caller commits."""
    session.logout_at = now
    session.status = ENDED
    work_date = as_utc(session.login_at).date() if session.login_at else now.date()
    upsert_subtask_time_log(
        db, session.project_id, session.subtask_id, session.employee_id, work_date, session.active_seconds
    )
