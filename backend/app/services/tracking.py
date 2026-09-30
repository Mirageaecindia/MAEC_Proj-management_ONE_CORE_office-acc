"""Subtask Login/Logout tracking: an engineer's worked time is Logout − Login.

The engineer logs in to a subtask and logs out when they stop. Idle time and
work in other programs (Revit, AutoCAD) count; nothing is measured in the
browser. While a session is open, every open tab of the app sends a heartbeat
each minute, even minimised, and the server records when it last heard from
the engineer (`last_seen_at`) and when they last *visited* the app: a click, a
key press or switching to its tab (`last_active_at`).

A silence longer than HEARTBEAT_GRACE means the laptop was switched off, asleep
or offline. The session is then closed at the last heartbeat, and when the app
is open again a new session on the same subtask starts by itself: the time the
laptop was off is not counted and the engineer doesn't have to log in again.

The day's work time (decided 2026-09-30) is everything the engineer banked that
day on any subtask of any project, plus the running session. Before it reaches
the daily mark nothing but the engineer's own Logout ends a session. Past the
mark every hour still counts (overtime is banked, the day's approval decides),
but the engineer must visit the app at least every VISIT_GRACE; otherwise the
session is closed at their last visit (or at the mark, if that came later) and
does not resume by itself. A forgotten Logout costs at most the grace.

Only one session runs at a time. Logging in to another subtask while one is
running is a switch: with the engineer's confirmation the running session ends
and the new one starts in the same moment, so switching is one step and hours
land on the subtask actually being worked on.

A session's time always goes to the day it started, and a pause is only ever
resumed on that same calendar day: the next morning the engineer logs in afresh,
so yesterday's subtask never carries on by itself. A day's row that has been
reviewed is never changed by a later Logout (review waits for the day's
sessions to close, see app/services/hours_review.py).

One rule (`settle`) decides all of this, applied by the heartbeat when the
engineer is back and by a server-side sweep every few minutes when they are
not, so a closed browser never leaves a session open for long.
"""

import asyncio
import logging
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
from app.domain.timesheets import DAILY_MARK_HOURS, PENDING_REVIEW
from app.repositories.tracking import ACTIVE, ENDED, TrackingRepository
from app.services.access import user_can_access_project
from app.services.governance_monitor import enforce_governance

log = logging.getLogger(__name__)

HEARTBEAT_GRACE = timedelta(minutes=5)  # the browser beats every minute; background tabs can lag
DAILY_MARK_SECONDS = DAILY_MARK_HOURS * 3600  # past this, the visit rule applies
VISIT_GRACE = timedelta(minutes=30)
SWEEP_INTERVAL = timedelta(minutes=5)
UNATTENDED_GAP = timedelta(hours=2)  # a session the system closed this long after the last visit is flagged

# TimeSession.ended_by
BY_ENGINEER = "engineer"  # pressed Logout
LAPTOP_OFF = "laptop_off"  # heartbeats stopped; closed at the last one and resumed on the next
NO_VISIT = "no_visit"  # past the daily mark without a visit for VISIT_GRACE; closed at the last visit
SUBTASK_DELETED = "subtask_deleted"  # the subtask was deleted while the engineer was logged in
PROJECT_ARCHIVED = "project_archived"  # the BU Head archived the project while the engineer was logged in


def utcnow() -> datetime:
    return datetime.now(UTC)


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
    if entry.approval_status != PENDING_REVIEW:
        # Can't happen: a day is not reviewed while one of its sessions is open. A reviewed
        # row is never changed; the session keeps its own record of the time.
        log.error(
            "Hours for a reviewed day were not banked: entry %s (%s), %s h from a late session",
            entry.id,
            entry.approval_status,
            hours,
        )
        return None
    entry.hours = round((entry.hours or 0) + hours, 2)
    return entry


def end_session(
    db: Session, session: models.TimeSession, now: datetime, ended_by: str, at: datetime | None = None
) -> int:
    """Close a session and bank its worked time, all of it, on the day it started. It ends
    at `at` when given, otherwise now, or at the last heartbeat when the browser has been
    silent too long (laptop off). Returns the seconds banked. The caller commits."""
    login_at, last_seen = as_utc(session.login_at), as_utc(session.last_seen_at)
    if at is None:
        at = now if now - last_seen <= HEARTBEAT_GRACE else last_seen
    seconds = max(0, int((at - login_at).total_seconds()))
    session.logout_at, session.status, session.active_seconds, session.ended_by = at, ENDED, seconds, ended_by
    upsert_subtask_time_log(db, session.project_id, session.subtask_id, session.employee_id, login_at.date(), seconds)
    return seconds


def last_visit(session: models.TimeSession) -> datetime:
    return as_utc(session.last_active_at or session.login_at)


def unattended_seconds(session: models.TimeSession) -> int:
    """Seconds between the engineer's last visit and the end of a closed session, when that
    is long enough (UNATTENDED_GAP) for the reviewer to look at; otherwise 0."""
    if session.logout_at is None:
        return 0
    gap = as_utc(session.logout_at) - max(last_visit(session), as_utc(session.login_at))
    return int(gap.total_seconds()) if gap > UNATTENDED_GAP else 0


def node_label(node: models.WbsNode | None) -> str:
    return " ".join(filter(None, [node.wbs_code, node.task_name])) if node is not None else "another subtask"


class TrackingService:
    def __init__(self, db: Session, sessions: TrackingRepository):
        self.db = db
        self.sessions = sessions

    # -- the engineer's calls -------------------------------------------------------------

    def heartbeat(self, user: models.User, last_active_at: datetime | None = None) -> dict:
        """The app is open: keep the session alive, resume it after the laptop was off, or
        end it when the engineer is past the daily mark and hasn't visited for VISIT_GRACE."""
        employee_id = _employee_id(user)
        now = utcnow()
        session = self.sessions.active_session(employee_id)
        try:
            if session is None:
                resumed = self._resume_after_pause(user, now)
                self.db.commit()
                return self._state_for(resumed, employee_id, now)
            silent = now - as_utc(session.last_seen_at) > HEARTBEAT_GRACE
            if last_active_at is not None and not silent:
                # The browser's clock may run ahead: never later than now. A visit reported after
                # a silence is the engineer coming back: it says nothing about the gap, which is
                # judged on the visits known before it.
                session.last_active_at = max(last_visit(session), min(as_utc(last_active_at), now))
            ended = self.settle(session, now, engineer_back=True)
            if ended is None:
                session.last_seen_at = now
                self.db.commit()
                return self._state_for(session, employee_id, now)
            self.db.flush()
            resumed = self._resume(user, session, now) if ended == LAPTOP_OFF else None
            self.db.commit()
        except StaleDataError:  # another tab's heartbeat got there first; its result stands
            self.db.rollback()
            return self._state_for(self.sessions.active_session(employee_id), employee_id, now)
        enforce_governance(self.db, session.project_id)
        return self._state_for(resumed, employee_id, now)

    def start(self, user: models.User, subtask_id: int, switch: bool = False) -> dict:
        """Log in to a subtask. With `switch`, a session running on another subtask ends now
        and this one starts in the same moment; without it, that case is refused."""
        _employee_id(user)
        node = self.sessions.node(subtask_id)
        if node is None:
            raise NotFoundError("Subtask not found.")
        refusal = self._refusal(user, node)
        if refusal is not None:
            raise refusal
        now = utcnow()
        running = self.sessions.active_session(user.employee_id)
        if running is not None:
            if running.subtask_id == node.id:
                raise ConflictError("You are already logged in to this subtask.")
            if not switch:
                label = node_label(self.sessions.node(running.subtask_id))
                raise ConflictError(f"You are logged in to '{label}'. Log out there first, or switch to this subtask.")
            running.last_active_at = now  # switching is a visit
            end_session(self.db, running, now, BY_ENGINEER)
            self.db.flush()
        session = self._open(user, node, now)
        self.db.commit()
        if running is not None:
            enforce_governance(self.db, running.project_id)
        return self._state_for(session, user.employee_id, now)  # with the over-8 state, at once

    def logout(self, user: models.User) -> dict:
        session = self.sessions.active_session(_employee_id(user))
        if session is None:  # already logged out, e.g. from another tab
            return self._state(None, over_mark=False)
        now = utcnow()
        try:
            mark_at = self._mark_at(session)
            if now - as_utc(session.last_seen_at) <= HEARTBEAT_GRACE:
                session.last_active_at = now  # pressing Logout is a visit
            end_session(self.db, session, now, BY_ENGINEER)
            self.db.commit()
        except StaleDataError:
            self.db.rollback()
            return self.logout(user)  # retry on the fresh state (the session may have resumed)
        enforce_governance(self.db, session.project_id)  # hours on an approved day count at once
        return self._state(None, over_mark=mark_at <= as_utc(session.logout_at))

    # -- the rule ---------------------------------------------------------------------------

    def settle(self, session: models.TimeSession, now: datetime, *, engineer_back: bool) -> str | None:
        """Apply the rules to one open session and return how it ended, or None when it
        stays open. `engineer_back`: a heartbeat just arrived (a silent session then pauses
        and resumes at once); the sweep passes False and leaves a short break alone."""
        last_seen = as_utc(session.last_seen_at)
        silent = now - last_seen > HEARTBEAT_GRACE
        mark_at = self._mark_at(session)
        if mark_at <= (last_seen if silent else now):  # past the daily mark
            since = max(last_visit(session), mark_at)  # time before the mark is never questioned
            if now - since > VISIT_GRACE:
                end_session(self.db, session, now, NO_VISIT, at=since)
                return NO_VISIT
            if silent and not engineer_back:
                return None  # a short break: the engineer may be back within the grace
        if silent:
            end_session(self.db, session, now, LAPTOP_OFF)  # at the last heartbeat
            return LAPTOP_OFF
        return None

    def sweep(self, now: datetime | None = None) -> int:
        """Settle every session whose browser has gone quiet, so a closed laptop never
        leaves hours unbanked. Runs every SWEEP_INTERVAL (see `sweep_forever`).
        Returns how many sessions it closed."""
        now = now or utcnow()
        closed, projects = 0, set()
        for session in self.sessions.silent_sessions(now - HEARTBEAT_GRACE):
            if self.settle(session, now, engineer_back=False) is not None:
                closed += 1
                projects.add(session.project_id)
        self.db.commit()
        for project_id in projects:
            enforce_governance(self.db, project_id)
        return closed

    def _mark_at(self, session: models.TimeSession) -> datetime:
        """When this session takes the engineer's day past the mark (its login, if the
        day was already there)."""
        login_at = as_utc(session.login_at)
        banked = self.sessions.banked_seconds(session.employee_id, login_at.date())
        return login_at + timedelta(seconds=max(0, DAILY_MARK_SECONDS - banked))

    # -- state and resuming ---------------------------------------------------------------

    def _state(self, session: models.TimeSession | None, **extra) -> dict:
        """What the Task Details page needs: which subtask the engineer is logged in to (no durations)."""
        active = None
        if session is not None:
            active = {
                "id": session.id,
                "project_id": session.project_id,
                "task_id": session.task_id,
                "subtask_id": session.subtask_id,
                "subtask_name": node_label(self.sessions.node(session.subtask_id)),
                "login_at": session.login_at,
            }
        return {"active_session": active, **extra}

    def _state_for(self, session: models.TimeSession | None, employee_id: int, now: datetime) -> dict:
        if session is not None:
            return self._state(session, over_mark=self._mark_at(session) <= now)
        return self._state(None, system_logout=self._system_logout(employee_id, now))

    def _system_logout(self, employee_id: int, now: datetime) -> dict | None:
        """The engineer's last session today, when the system ended it for want of a visit."""
        last = self.sessions.last_session(employee_id)
        if last is None or last.ended_by != NO_VISIT or as_utc(last.logout_at).date() != now.date():
            return None
        day_seconds = self.sessions.banked_seconds(employee_id, as_utc(last.login_at).date())
        return {
            "at": as_utc(last.logout_at),
            "project_id": last.project_id,
            "subtask_id": last.subtask_id,
            "day_hours": round(day_seconds / 3600, 2),
        }

    def _resume_after_pause(self, user: models.User, now: datetime) -> models.TimeSession | None:
        """The sweep paused the session while the laptop was off: carry on where it left off."""
        last = self.sessions.last_session(user.employee_id)
        return self._resume(user, last, now) if last is not None and last.ended_by == LAPTOP_OFF else None

    def _resume(self, user: models.User, paused: models.TimeSession, now: datetime) -> models.TimeSession | None:
        if as_utc(paused.logout_at).date() != now.date():
            return None  # never across a calendar day: the engineer logs in afresh
        node = self.sessions.node(paused.subtask_id)
        if node is None or self._refusal(user, node) is not None:
            paused.ended_by = BY_ENGINEER  # nothing to come back to: the pause is final
            return None
        return self._open(user, node, now)

    def _refusal(self, user: models.User, node: models.WbsNode) -> DomainError | None:
        """Why the engineer can't log in to this subtask at all, or None (a running session
        elsewhere is `start`'s business: it may be a switch)."""
        if node.parent_id is None:
            return BadRequestError("Login/Logout is for subtasks. Open one of this task's subtasks.")
        if node.assigned_engineer_id != user.employee_id:
            return ForbiddenError("You can only log in to subtasks assigned to you.")
        project = self.sessions.project(node.project_id)
        if project is None or not user_can_access_project(self.db, user, project):
            return ForbiddenError(NO_PROJECT_ACCESS)
        if project.timesheets_soft_locked:
            return ConflictError("Timesheets are soft-locked by the BU Head, so working time can't be tracked.")
        return None

    def _open(self, user: models.User, node: models.WbsNode, now: datetime) -> models.TimeSession:
        session = models.TimeSession(
            project_id=node.project_id,
            task_id=node.parent_id,
            subtask_id=node.id,
            employee_id=user.employee_id,
            login_at=now,
            last_seen_at=now,
            last_active_at=now,  # logging in is a visit
            status=ACTIVE,
        )
        self.db.add(session)
        return session


async def sweep_forever(session_factory, interval: timedelta = SWEEP_INTERVAL) -> None:
    """Background task started with the app: settle silent sessions every `interval`."""
    while True:
        await asyncio.sleep(interval.total_seconds())
        db = session_factory()
        try:
            TrackingService(db, TrackingRepository(db)).sweep()
        except Exception:  # the next tick tries again; never let the loop die
            log.exception("tracking sweep failed")
            db.rollback()
        finally:
            db.close()


def _employee_id(user: models.User) -> int:
    if user.employee_id is None:
        raise ForbiddenError("Your account is not linked to an employee record.")
    return user.employee_id
