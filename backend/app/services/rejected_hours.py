"""A second look at rejected hours (decided 2026-09-30).

Each project has a list of the hours rejected in the last seven days, with who
rejected them and why. Any lead of the project, or the BU Head, may approve
them again from that list, so a rejection that was wrong or too harsh can be
put right without the engineer doing anything. After seven days a rejection is
final: nobody can approve those hours.

Guards:
- hours the BU Head rejected are approved again only by the BU Head;
- nobody approves their own hours;
- a row is approved again from the list once: after that only the BU Head takes the
  hours back or approves them again, so two leads can't reverse each other in turn;
- a reason is required, and the decision is audited with both names
  (`hours_reapproved`, shown on the dashboards);
- an unattended day can be approved up to the engineer's last visit;
- the seven days count only while the project is open: time during which it
  was soft-locked or archived is not counted, and nothing is approved while
  it is locked.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import models
from app.core.errors import NO_PROJECT_ACCESS, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.core.security import as_utc
from app.domain.timesheets import APPROVED, REAPPROVAL_WINDOW, REJECTED, open_time
from app.services.access import LEAD, project_role
from app.services.governance_monitor import enforce_governance
from app.services.hours_review import (
    NOTHING_ATTENDED,
    NOTHING_UNATTENDED,
    REAPPROVED_ONCE,
    row_key,
    sessions_by_row,
    tasks_by_id,
    trimmed_hours,
)

HOURS_REAPPROVED = "hours_reapproved"  # GovernanceAction.action

# Audit actions that stop and restart the seven-day clock: (what paused it, pausing?).
CLOCK_EVENTS = {
    "stop_execution": ("lock", True),
    "auto_lock": ("lock", True),
    "resume_execution": ("lock", False),
    "archive": ("archive", True),
    "unarchive": ("archive", False),
}

LEADS_ONLY = "Rejected hours are reviewed by the project's leads and the BU Head."
NOT_REJECTED = "Only rejected hours can be approved again."
OWN_HOURS = "Nobody approves their own hours."
BU_HEAD_REJECTED = "These hours were rejected by the BU Head, so only the BU Head can approve them again."
FINAL = "These hours were rejected more than 7 days ago. The rejection is final."
REASON_NEEDED = "Give a reason for approving hours that were rejected."
LOCKED = "The project is locked or archived, so hours can't be approved. The 7 days don't run meanwhile."


class RejectedHours:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user: models.User, project_id: int, now: datetime) -> list[dict]:
        """The project's rejected hours that can still be approved again, oldest deadline first."""
        project = self._project_for(user, project_id)
        events = self._clock_events(project.id)
        entry = models.TimeLogEntry
        # Nothing older than the window plus all the time the project was ever closed can be open.
        ever_closed = (now - events[0][0]) - open_time(events[0][0], now, events) if events else timedelta(0)
        rows = (
            self.db.query(entry)
            .filter(
                entry.project_id == project.id,
                entry.approval_status == REJECTED,
                entry.reviewed_at >= now - REAPPROVAL_WINDOW - ever_closed,
            )
            .all()
        )
        open_rows = [(row, left) for row in rows if (left := self._time_left(row, events, now)) > timedelta(0)]
        if not open_rows:
            return []
        entries = [row for row, _ in open_rows]
        tasks = tasks_by_id(self.db, entries)
        names = dict(
            self.db.query(models.Employee.id, models.Employee.name).filter(
                models.Employee.id.in_({row.employee_id for row in entries})
            )
        )
        by_bu_head = self._rejected_by_bu_head(entries)
        sessions = sessions_by_row(self.db, entries)
        out = []
        for row, left in sorted(open_rows, key=lambda pair: pair[1]):
            task = tasks.get(row.task_id)
            unattended = trimmed_hours(sessions.get(row_key(row), [])) if row.trimmed_hours is None else 0
            out.append(
                {
                    "id": row.id,
                    "project_id": row.project_id,
                    "task_id": row.task_id,
                    "wbs_code": task.wbs_code if task else None,
                    "task_name": task.task_name if task else row.task_name or "",
                    "employee_id": row.employee_id,
                    "employee_name": names.get(row.employee_id, ""),
                    "work_date": row.work_date.isoformat(),
                    "hours": round(float(row.hours or 0), 2),
                    "rejected_by": row.reviewed_by,
                    "rejected_by_bu_head": by_bu_head[row.id],
                    "rejected_at": as_utc(row.reviewed_at),
                    "reason": row.review_reason,
                    "hours_left": round(left.total_seconds() / 3600, 1),  # of the seven days, while the project is open
                    "clock_paused": bool(project.timesheets_soft_locked or project.archived_at),
                    "unattended": unattended > 0,
                    "attended_hours": round(row.hours - unattended, 2) if unattended > 0 else None,
                    "can_reapprove": self._refusal(user, project, row, by_bu_head[row.id]) is None,
                }
            )
        return out

    def reapprove(
        self, user: models.User, entry_id: int, reason: str | None, attended_only: bool, now: datetime
    ) -> dict:
        """Approve rejected hours again, wholly or only up to the engineer's last visit."""
        entry = self.db.get(models.TimeLogEntry, entry_id)
        if entry is None:
            raise NotFoundError("Time log entry not found.")
        project = self._project_for(user, entry.project_id)
        if entry.approval_status != REJECTED:
            raise ConflictError(NOT_REJECTED)
        refusal = self._refusal(user, project, entry, self._rejected_by_bu_head([entry])[entry.id])
        if refusal is not None:
            raise refusal
        if self._time_left(entry, self._clock_events(project.id), now) <= timedelta(0):
            raise ConflictError(FINAL)
        reason = (reason or "").strip()
        if not reason:
            raise BadRequestError(REASON_NEEDED)

        logged = entry.hours
        if attended_only:
            trimmed = trimmed_hours(sessions_by_row(self.db, [entry]).get(row_key(entry), []))
            if trimmed <= 0:
                raise BadRequestError(NOTHING_UNATTENDED)
            if logged - trimmed <= 0:
                raise BadRequestError(NOTHING_ATTENDED)
            entry.hours, entry.trimmed_hours = round(logged - trimmed, 2), trimmed
        approver = user.full_name or user.username
        task = self.db.get(models.WbsNode, entry.task_id)
        task_name = task.task_name if task is not None else entry.task_name or f"task #{entry.task_id}"
        was = f"rejected by {entry.reviewed_by or 'an earlier reviewer'}" + (
            f": {entry.review_reason}" if entry.review_reason else ""
        )
        part = f"{entry.hours:g} of {logged:g} h" if attended_only else f"{logged:g} h"
        self.db.add(
            models.GovernanceAction(
                project_id=entry.project_id,
                action=HOURS_REAPPROVED,
                comments=f"{part} on {entry.work_date.isoformat()} ({task_name}): {reason} ({was})",
                created_by=approver,
            )
        )
        entry.approval_status, entry.reviewed_by, entry.reviewed_by_user_id, entry.reviewed_at = (
            APPROVED,
            approver,
            user.id,
            now,
        )
        entry.review_reason = f"Approved again: {reason} ({was})"
        entry.reapproved_at = now
        self.db.commit()
        enforce_governance(self.db, entry.project_id)  # usage = approved hours: alerts / auto-lock
        return {
            "id": entry.id,
            "approval_status": entry.approval_status,
            "hours": entry.hours,
            "trimmed_hours": entry.trimmed_hours,
            "reviewed_by": entry.reviewed_by,
            "review_reason": entry.review_reason,
        }

    # -- rules -------------------------------------------------------------------------------

    def _refusal(
        self, user: models.User, project: models.Project, entry: models.TimeLogEntry, by_bu_head: bool
    ) -> ForbiddenError | ConflictError | None:
        """Why this user can't approve these rejected hours again (the deadline aside), or None."""
        if user.employee_id is not None and user.employee_id == entry.employee_id:
            return ForbiddenError(OWN_HOURS)
        if by_bu_head and user.role != Role.BU_HEAD:
            return ForbiddenError(BU_HEAD_REJECTED)
        if entry.reapproved_at is not None and user.role != Role.BU_HEAD:
            return ForbiddenError(REAPPROVED_ONCE)
        if project.timesheets_soft_locked or project.archived_at:
            return ConflictError(LOCKED)
        return None

    def _time_left(self, entry: models.TimeLogEntry, events: list, now: datetime) -> timedelta:
        """What remains of the seven days, counting only the time the project was open."""
        if entry.reviewed_at is None:
            return timedelta(0)
        return REAPPROVAL_WINDOW - open_time(as_utc(entry.reviewed_at), now, events)

    def _clock_events(self, project_id: int) -> list[tuple[datetime, str, bool]]:
        action = models.GovernanceAction
        rows = (
            self.db.query(action.created_at, action.action)
            .filter(action.project_id == project_id, action.action.in_(CLOCK_EVENTS))
            .order_by(action.created_at, action.id)
        )
        return [(as_utc(at), *CLOCK_EVENTS[name]) for at, name in rows]

    def _rejected_by_bu_head(self, entries: list[models.TimeLogEntry]) -> dict[int, bool]:
        """Entry id -> the BU Head rejected it. An unknown reviewer counts as the BU Head (the stricter rule)."""
        ids = {entry.reviewed_by_user_id for entry in entries} - {None}
        roles = dict(self.db.query(models.User.id, models.User.role).filter(models.User.id.in_(ids))) if ids else {}
        return {entry.id: roles.get(entry.reviewed_by_user_id, Role.BU_HEAD) == Role.BU_HEAD for entry in entries}

    def _project_for(self, user: models.User, project_id: int) -> models.Project:
        project = self.db.get(models.Project, project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        role = project_role(self.db, user, project.id)
        if role is None:
            raise ForbiddenError(NO_PROJECT_ACCESS)
        if role not in (Role.BU_HEAD, LEAD):
            raise ForbiddenError(LEADS_ONLY)
        return project
