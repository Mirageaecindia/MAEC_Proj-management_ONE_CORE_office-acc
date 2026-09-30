"""Who approves which hours, and the decisions themselves (decided 2026-09-28).

Hours are approved per day, per subtask, per engineer:
1. A project lead's own hours: the BU Head.
2. Otherwise the lead of the row's task, while they lead the project and
   their lead period hasn't ended.
3. Otherwise (the task has no lead, its lead was replaced or their period is
   over, or the lead is the engineer themselves): the BU Head.
Nobody approves their own hours, and no hours are left without a reviewer.

Only finished days are reviewed, and only once every session the engineer
started on that day has closed, so a reviewed row never changes afterwards.
Usage counts each day as it is approved; the week is nothing more than the sum
of its days.

A session the system closed long after the engineer's last visit is flagged
"unattended" on its day's row. The reviewer may then approve the day only up to
the last visit: the rest stays on the row as trimmed hours and in the audit log.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ConflictError, ForbiddenError
from app.core.roles import Role
from app.core.security import as_utc
from app.domain.timesheets import (
    APPROVED,
    PENDING_REVIEW,
    REASON_REQUIRED,
    over_mark,
    review_transition,
    reviewable,
)
from app.repositories.tracking import ACTIVE, ENDED
from app.services.tracking import unattended_seconds

BU_HEAD = None  # reviewer id meaning "the BU Head"
NOT_YOUR_HOURS = (
    "These hours are approved by the task's lead, or by the BU Head when the task has no active lead "
    "or they are a project lead's own."
)
DAY_NOT_OVER = "A day is reviewed once it is over (yesterday or earlier)."
REAPPROVED_ONCE = "These hours were rejected and approved again once already. From here only the BU Head decides them."
SESSION_STILL_OPEN = (
    "The engineer is still logged in to a session started on that day. Review it once the session has closed."
)
NOTHING_UNATTENDED = "No unattended time on this day: approve or reject it as a whole."
NOTHING_ATTENDED = "Nothing on this day was attended: reject it instead."
HOURS_UNAPPROVED = "hours_unapproved"  # GovernanceAction.action: approved hours taken back, with the reason
HOURS_PARTLY_APPROVED = "hours_partly_approved"  # GovernanceAction.action: approved up to the last visit

RowKey = tuple[int, int, date]  # (subtask id, employee id, day)


def tasks_by_id(db: Session, entries: Iterable[models.TimeLogEntry]) -> dict[int, models.WbsNode]:
    ids = {entry.task_id for entry in entries}
    return {node.id: node for node in db.query(models.WbsNode).filter(models.WbsNode.id.in_(ids))} if ids else {}


def row_key(entry: models.TimeLogEntry) -> RowKey:
    return entry.task_id, entry.employee_id, entry.work_date


def sessions_by_row(db: Session, entries: Iterable[models.TimeLogEntry]) -> dict[RowKey, list[models.TimeSession]]:
    """The closed Login/Logout sessions behind each day's row, in one query."""
    entries = list(entries)
    if not entries:
        return {}
    days = [entry.work_date for entry in entries]
    session = models.TimeSession
    rows = (
        db.query(session)
        .filter(
            session.status == ENDED,
            session.subtask_id.in_({entry.task_id for entry in entries}),
            session.employee_id.in_({entry.employee_id for entry in entries}),
            session.login_at >= datetime.combine(min(days), time.min, tzinfo=UTC),
            session.login_at < datetime.combine(max(days) + timedelta(days=1), time.min, tzinfo=UTC),
        )
        .order_by(session.login_at)
    )
    grouped: dict[RowKey, list[models.TimeSession]] = defaultdict(list)
    for row in rows:
        grouped[(row.subtask_id, row.employee_id, as_utc(row.login_at).date())].append(row)
    return grouped


def trimmed_hours(sessions: Iterable[models.TimeSession]) -> float:
    """Hours between the last visit and the close of the row's unattended sessions."""
    return round(sum(unattended_seconds(session) for session in sessions) / 3600, 2)


class HoursReview:
    """The reviewer rule for one project, loaded once (two small queries) and applied to any number of rows."""

    def __init__(self, db: Session, project: models.Project, today: date):
        self.db = db
        self.project = project
        self.today = today
        lead_ids = {
            project.project_lead_electrical_user_id,
            project.project_lead_mechanical_user_id,
            project.project_lead_bim_user_id,
        } - {None}
        rows = db.query(models.User.id, models.User.employee_id).filter(models.User.id.in_(lead_ids)).all()
        self._employee_of_lead = {user_id: employee_id for user_id, employee_id in rows}
        self.lead_employee_ids = set(self._employee_of_lead.values()) - {None}
        ended = {
            employee_id
            for (employee_id,) in db.query(models.ResourceBooking.employee_id).filter(
                models.ResourceBooking.project_id == project.id,
                models.ResourceBooking.role == "lead",
                models.ResourceBooking.end_date < today,
            )
        }
        self._active_leads = {user_id for user_id, employee_id in rows if employee_id not in ended}
        open_sessions = db.query(models.TimeSession.employee_id, models.TimeSession.login_at).filter_by(status=ACTIVE)
        self._open_days = {(employee_id, as_utc(login_at).date()) for employee_id, login_at in open_sessions}

    def session_open(self, entry: models.TimeLogEntry) -> bool:
        """The engineer still has a session running that started on the row's day."""
        return (entry.employee_id, entry.work_date) in self._open_days

    def reviewer(self, task: models.WbsNode | None, employee_id: int, remembered_lead: int | None = None) -> int | None:
        """The user id who approves this engineer's hours on this task, or BU_HEAD. A deleted
        task's rows remember its lead (`remembered_lead`), so a cleanup changes nothing."""
        if employee_id in self.lead_employee_ids:
            return BU_HEAD
        lead = task.assigned_lead_user_id if task is not None else remembered_lead
        if lead not in self._active_leads or self._employee_of_lead.get(lead) == employee_id:
            return BU_HEAD
        return lead

    def may_review(
        self, user: models.User, task: models.WbsNode | None, employee_id: int, remembered_lead: int | None = None
    ) -> bool:
        reviewer = self.reviewer(task, employee_id, remembered_lead)
        return user.role == Role.BU_HEAD if reviewer is BU_HEAD else reviewer == user.id

    def may_decide(self, user: models.User, entry: models.TimeLogEntry, task: models.WbsNode | None) -> bool:
        """Whether `user` decides this row: its reviewer, except that a row already approved
        again from the rejected list (app/services/rejected_hours.py) belongs to the BU Head alone."""
        if entry.reapproved_at is not None:
            return user.role == Role.BU_HEAD
        return self.may_review(user, task, entry.employee_id, entry.task_lead_user_id)

    def review(
        self,
        user: models.User,
        entry: models.TimeLogEntry,
        task: models.WbsNode | None,
        action: str,
        reason: str | None,
        now: datetime,
    ) -> None:
        """One decision on one day's hours. The caller checks the project lock and commits."""
        if not self.may_decide(user, entry, task):
            raise ForbiddenError(REAPPROVED_ONCE if entry.reapproved_at is not None else NOT_YOUR_HOURS)
        if not reviewable(entry.work_date, self.today):
            raise ConflictError(DAY_NOT_OVER)
        if self.session_open(entry):
            raise ConflictError(SESSION_STILL_OPEN)
        problem = review_transition(entry.approval_status, action, reason)
        if problem == REASON_REQUIRED:
            raise BadRequestError(problem)
        if problem:
            raise ConflictError(problem)
        reviewer = user.full_name or user.username
        if entry.approval_status == APPROVED:  # taken back: audited, shown on the BU Head's dashboard
            task_name = task.task_name if task is not None else f"task #{entry.task_id}"
            self.db.add(
                models.GovernanceAction(
                    project_id=entry.project_id,
                    action=HOURS_UNAPPROVED,
                    comments=f"{entry.hours:g} h on {entry.work_date.isoformat()} ({task_name}) rejected: {reason}",
                    created_by=reviewer,
                )
            )
        entry.approval_status, entry.reviewed_by, entry.reviewed_at = action, reviewer, now
        entry.reviewed_by_user_id = user.id  # who may approve rejected hours again depends on who rejected them
        entry.review_reason = (reason or "").strip() or None

    def approve_attended(
        self,
        user: models.User,
        entry: models.TimeLogEntry,
        task: models.WbsNode | None,
        sessions: Iterable[models.TimeSession],
        now: datetime,
    ) -> None:
        """Approve a pending day only up to the engineer's last visit. The unattended rest
        stays on the row as trimmed hours and is audited. Same guards as `review`."""
        trimmed = trimmed_hours(sessions)
        if trimmed <= 0:
            raise BadRequestError(NOTHING_UNATTENDED)
        logged = entry.hours
        attended = round(logged - trimmed, 2)
        if attended <= 0:
            raise BadRequestError(NOTHING_ATTENDED)
        self.review(user, entry, task, APPROVED, None, now)
        entry.hours, entry.trimmed_hours = attended, trimmed
        task_name = task.task_name if task is not None else entry.task_name or f"task #{entry.task_id}"
        entry.review_reason = (
            f"Approved up to the last visit: {attended:g} of {logged:g} h; {trimmed:g} h unattended not approved."
        )
        self.db.add(
            models.GovernanceAction(
                project_id=entry.project_id,
                action=HOURS_PARTLY_APPROVED,
                comments=f"{entry.work_date.isoformat()} ({task_name}): {entry.review_reason}",
                created_by=entry.reviewed_by,
            )
        )

    def review_pending(
        self,
        user: models.User,
        entries: Iterable[models.TimeLogEntry],
        tasks: dict[int, models.WbsNode],
        action: str,
        now: datetime,
        reason: str | None = None,
    ) -> tuple[int, int, int]:
        """Bulk: every pending, finished day among `entries` that `user` is responsible for,
        except the days someone has to look at: over the mark (overtime is pay-relevant) and
        unattended. Returns (decided, skipped as over the mark, skipped as unattended)."""
        mine = [
            entry
            for entry in entries
            if entry.approval_status == PENDING_REVIEW
            and reviewable(entry.work_date, self.today)
            and not self.session_open(entry)
            and self.may_decide(user, entry, tasks.get(entry.task_id))
        ]
        sessions = sessions_by_row(self.db, mine)
        over = [entry for entry in mine if over_mark(entry)]
        unattended = [
            entry for entry in mine if not over_mark(entry) and trimmed_hours(sessions.get(row_key(entry), [])) > 0
        ]
        held_back = {id(entry) for entry in (*over, *unattended)}
        decided = [entry for entry in mine if id(entry) not in held_back]
        for entry in decided:
            self.review(user, entry, tasks.get(entry.task_id), action, reason, now)
        return len(decided), len(over), len(unattended)
