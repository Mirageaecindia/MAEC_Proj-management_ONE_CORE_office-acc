"""Subtask Login/Logout tracking: an engineer's worked time is Logout − Login.

The engineer logs in to a subtask and logs out when they stop. Idle time and
work in other programs (Revit, AutoCAD) count; nothing is measured in the
browser. While a session is open, every open tab of the app sends a heartbeat
each minute, even minimised, and the server records when it last heard from
the engineer (`last_seen_at`).

A silence longer than HEARTBEAT_GRACE means the laptop was switched off, asleep
or offline. The session is then closed at the last heartbeat, and when the app
is open again a new session on the same subtask starts by itself: the time the
laptop was off is not counted and the engineer doesn't have to log in again.

On Logout the worked time is banked into the weekly time-log row for the day
the session started (at most DAILY_LIMIT a day); the Lead's approval decides
what counts toward the project's usage.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import models
from app.core.errors import (
    NO_PROJECT_ACCESS,
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import as_utc
from app.domain.timesheets import PENDING_REVIEW
from app.repositories.tracking import ACTIVE, ENDED, TrackingRepository
from app.services.access import user_can_access_project
from app.services.governance_monitor import enforce_governance

HEARTBEAT_GRACE = timedelta(minutes=5)  # the browser beats every minute; background tabs can lag
DAILY_LIMIT_SECONDS = 8 * 3600


def upsert_subtask_time_log(
    db: Session, project_id: int, task_id: int, employee_id: int, day: date, seconds: int
) -> models.TimeLogEntry | None:
    """Fold worked seconds into the day's row (project x subtask x engineer x day)
    that the task's lead approves. Every day is banked; approval decides what stands."""
    hours = round(seconds / 3600, 2)
    if hours <= 0:
        return None
    entry = (
        db.query(models.TimeLogEntry)
        .filter_by(project_id=project_id, task_id=task_id, employee_id=employee_id, work_date=day)
        .first()
    )
    if entry is None:
        entry = models.TimeLogEntry(
            project_id=project_id,
            task_id=task_id,
            employee_id=employee_id,
            work_date=day,
            hours=0,
            approval_status=PENDING_REVIEW,
        )
        db.add(entry)
    entry.hours = round((entry.hours or 0) + hours, 2)
    if entry.approval_status != PENDING_REVIEW:
        # More hours on a reviewed day (a session that started the day before) need review too.
        entry.approval_status, entry.reviewed_by, entry.reviewed_at = PENDING_REVIEW, None, None
    return entry


def end_session(db: Session, session: models.TimeSession, now: datetime) -> bool:
    """Log a session out and bank its worked time. It ends now, or at the last
    heartbeat when the browser has been silent too long (laptop off). Returns
    True when the daily limit cut the time short. The caller commits."""
    login_at, last_seen = as_utc(session.login_at), as_utc(session.last_seen_at)
    logout_at = now if now - last_seen <= HEARTBEAT_GRACE else last_seen
    work_date = login_at.date()
    worked = max(0, int((logout_at - login_at).total_seconds()))
    room = max(0, DAILY_LIMIT_SECONDS - TrackingRepository(db).banked_seconds(session.employee_id, work_date))
    seconds = min(worked, room)
    session.logout_at, session.status, session.active_seconds = logout_at, ENDED, seconds
    upsert_subtask_time_log(db, session.project_id, session.subtask_id, session.employee_id, work_date, seconds)
    return seconds < worked


def _state(session: models.TimeSession | None, **extra) -> dict:
    """What the Task Details page needs: which subtask the engineer is logged in to (no durations)."""
    active = None
    if session is not None:
        active = {
            "id": session.id,
            "project_id": session.project_id,
            "task_id": session.task_id,
            "subtask_id": session.subtask_id,
            "login_at": session.login_at,
        }
    return {"active_session": active, **extra}


class TrackingService:
    def __init__(self, db: Session, sessions: TrackingRepository):
        self.db = db
        self.sessions = sessions

    def heartbeat(self, user: models.User) -> dict:
        """The app is open: keep the session alive, or resume it after the laptop was off."""
        employee_id = _employee_id(user)
        session = self.sessions.active_session(employee_id)
        if session is None:
            return _state(None)
        now = datetime.now(UTC)
        try:
            if now - as_utc(session.last_seen_at) <= HEARTBEAT_GRACE:
                session.last_seen_at = now
                self.db.commit()
                return _state(session)
            end_session(self.db, session, now)
            self.db.flush()
            node = self.sessions.node(session.subtask_id)
            resumed = self._open(user, node, now) if node and self._refusal(user, node) is None else None
            self.db.commit()
        except StaleDataError:  # another tab's heartbeat got there first; its result stands
            self.db.rollback()
            return _state(self.sessions.active_session(employee_id))
        enforce_governance(self.db, session.project_id)
        return _state(resumed)

    def start(self, user: models.User, subtask_id: int) -> dict:
        _employee_id(user)
        node = self.sessions.node(subtask_id)
        if node is None:
            raise NotFoundError("Subtask not found.")
        refusal = self._refusal(user, node)
        if refusal is not None:
            raise refusal
        session = self._open(user, node, datetime.now(UTC))
        self.db.commit()
        return _state(session)

    def logout(self, user: models.User) -> dict:
        session = self.sessions.active_session(_employee_id(user))
        if session is None:  # already logged out, e.g. from another tab
            return _state(None, limit_reached=False)
        try:
            limit_reached = end_session(self.db, session, datetime.now(UTC))
            self.db.commit()
        except StaleDataError:
            self.db.rollback()
            return self.logout(user)  # retry on the fresh state (the session may have resumed)
        enforce_governance(self.db, session.project_id)  # hours on an approved row or week count at once
        return _state(None, limit_reached=limit_reached)

    def _refusal(self, user: models.User, node: models.WbsNode) -> DomainError | None:
        """Why the engineer can't log in to this subtask now, or None."""
        if node.parent_id is None:
            return BadRequestError("Login/Logout is for subtasks. Open one of this task's subtasks.")
        if node.assigned_engineer_id != user.employee_id:
            return ForbiddenError("You can only log in to subtasks assigned to you.")
        project = self.sessions.project(node.project_id)
        if project is None or not user_can_access_project(self.db, user, project):
            return ForbiddenError(NO_PROJECT_ACCESS)
        if project.timesheets_soft_locked:
            return ConflictError("Timesheets are soft-locked by the BU Head, so working time can't be tracked.")
        if self.sessions.active_session(user.employee_id) is not None:
            return ConflictError("You are already logged in to another subtask. Log out there first.")
        today = datetime.now(UTC).date()
        if self.sessions.banked_seconds(user.employee_id, today) >= DAILY_LIMIT_SECONDS:
            return ConflictError(f"You have reached the {DAILY_LIMIT_SECONDS // 3600}-hour daily limit.")
        return None

    def _open(self, user: models.User, node: models.WbsNode, now: datetime) -> models.TimeSession:
        session = models.TimeSession(
            project_id=node.project_id,
            task_id=node.parent_id,
            subtask_id=node.id,
            employee_id=user.employee_id,
            login_at=now,
            last_seen_at=now,
            status=ACTIVE,
        )
        self.db.add(session)
        return session


def _employee_id(user: models.User) -> int:
    if user.employee_id is None:
        raise ForbiddenError("Your account is not linked to an employee record.")
    return user.employee_id
