"""Corrections: hours logged on the wrong subtask (TODO H2, decided 2026-09-28 and 2026-09-30).

An engineer proposes "move N hours on day D from subtask X to subtask Y": both
their own subtasks on the same project, and only hours that are still pending
or were rejected. The reviewer of the *target* task decides, by the same rule
as hours approval (the task's lead; the BU Head when the engineer is that lead
or the task has no active lead), so nobody approves their own correction.

A correction only moves hours: the day's total is the same before and after.
The moved hours join the target's row for that day (a new row is pending; an
existing row keeps its status, so the reviewer who accepts hours into an
approved day is approving them). While a correction is pending, its source
row can't be approved.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

import models
from app.core.errors import NO_PROJECT_ACCESS, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.domain.timesheets import APPROVED, PENDING_REVIEW, REJECTED, today_utc
from app.services.access import ENGINEER, project_role
from app.services.governance_monitor import enforce_governance
from app.services.hours_review import HoursReview

PENDING, ACCEPTED, DECLINED, CANCELLED = "pending", "approved", "rejected", "cancelled"
RECENT = 50  # decided corrections listed after the pending ones

SAME_SUBTASK = "Choose a different subtask to move the hours to."
NOT_YOUR_SUBTASK = "You can only move hours between your own subtasks of this project."
NO_HOURS = "You have no hours on that subtask on that day."
ONLY_UNAPPROVED = "Approved hours can't be moved. Only pending or rejected hours can."
TOO_MANY = "You can't move more hours than the subtask has on that day."
STILL_LOGGED_IN = "Log out first: you still have a session running that started on that day."
ALREADY_PROPOSED = "A correction on these hours is already waiting for a decision."
TARGET_REJECTED = "Hours on the target subtask were rejected for that day. Choose another subtask."
NOT_YOUR_CORRECTION = (
    "A correction is decided by the lead of the task the hours move to, or by the BU Head when the engineer "
    "is that lead or the task has no active lead."
)
ALREADY_DECIDED = "This correction has already been decided."
HOURS_CHANGED = "The hours changed since this correction was proposed. Reject it, or ask for a new one."
LOCKED = "Timesheets are soft-locked by the BU Head, so corrections can't be approved."
NOT_YOURS_TO_CANCEL = "Only the engineer who proposed a correction can withdraw it."


class CorrectionService:
    def __init__(self, db: Session):
        self.db = db

    # -- the engineer ------------------------------------------------------------------------

    def propose(
        self, user: models.User, project_id: int, day: date, from_task_id: int, to_task_id: int, hours: float, note
    ) -> dict:
        project = self._project_for(user, project_id)
        if user.employee_id is None:
            raise ForbiddenError(NOT_YOUR_SUBTASK)
        if from_task_id == to_task_id:
            raise BadRequestError(SAME_SUBTASK)
        target = self.db.get(models.WbsNode, to_task_id)
        if (
            target is None
            or target.project_id != project.id
            or target.parent_id is None
            or target.assigned_engineer_id != user.employee_id
        ):
            raise ForbiddenError(NOT_YOUR_SUBTASK)
        source = self._row(project.id, from_task_id, user.employee_id, day)
        if source is None:
            raise NotFoundError(NO_HOURS)
        if source.approval_status == APPROVED:
            raise ConflictError(ONLY_UNAPPROVED)
        hours = round(hours, 2)
        if hours > source.hours:
            raise BadRequestError(TOO_MANY)
        review = HoursReview(self.db, project, today_utc())
        if review.session_open(source):
            raise ConflictError(STILL_LOGGED_IN)
        if review.correction_pending(source):
            raise ConflictError(ALREADY_PROPOSED)
        target_row = self._row(project.id, to_task_id, user.employee_id, day)
        if target_row is not None and target_row.approval_status == REJECTED:
            raise ConflictError(TARGET_REJECTED)
        correction = models.HoursCorrection(
            project_id=project.id,
            employee_id=user.employee_id,
            work_date=day,
            from_task_id=from_task_id,
            to_task_id=to_task_id,
            hours=hours,
            note=(note or "").strip() or None,
            status=PENDING,
            requested_by=user.full_name or user.username,
        )
        self.db.add(correction)
        self.db.commit()
        return self._outputs(user, project, [correction])[0]

    def cancel(self, user: models.User, correction_id: int) -> dict:
        correction = self._pending(correction_id)
        if user.employee_id is None or correction.employee_id != user.employee_id:
            raise ForbiddenError(NOT_YOURS_TO_CANCEL)
        correction.status = CANCELLED
        self.db.commit()
        return self._outputs(user, self.db.get(models.Project, correction.project_id), [correction])[0]

    # -- the reviewer ------------------------------------------------------------------------

    def decide(self, user: models.User, correction_id: int, accept: bool, reason: str | None, now: datetime) -> dict:
        correction = self._pending(correction_id)
        project = self._project_for(user, correction.project_id)
        review = HoursReview(self.db, project, today_utc())
        target = self.db.get(models.WbsNode, correction.to_task_id)
        if not review.may_review(user, target, correction.employee_id):
            raise ForbiddenError(NOT_YOUR_CORRECTION)
        if accept:
            if project.timesheets_soft_locked:
                raise ConflictError(LOCKED)
            self._move(correction)
        correction.status = ACCEPTED if accept else DECLINED
        correction.decided_by, correction.decided_at = user.full_name or user.username, now
        correction.decision_reason = (reason or "").strip() or None
        self.db.commit()
        if accept:
            enforce_governance(self.db, project.id)  # hours moved into an approved day count at once
        return self._outputs(user, project, [correction])[0]

    def _move(self, correction: models.HoursCorrection) -> None:
        """Take the hours off the source row and put them on the target's: the total never changes."""
        key = (correction.project_id, correction.employee_id, correction.work_date)
        source = self._row(key[0], correction.from_task_id, key[1], key[2])
        if source is None or source.approval_status == APPROVED or source.hours < correction.hours:
            raise ConflictError(HOURS_CHANGED)
        target = self._row(key[0], correction.to_task_id, key[1], key[2])
        if target is not None and target.approval_status == REJECTED:
            raise ConflictError(TARGET_REJECTED)
        if target is None:
            target = models.TimeLogEntry(
                project_id=key[0],
                task_id=correction.to_task_id,
                employee_id=key[1],
                work_date=key[2],
                hours=0,
                approval_status=PENDING_REVIEW,
            )
            self.db.add(target)
        target.hours = round(target.hours + correction.hours, 2)
        source.hours = round(source.hours - correction.hours, 2)
        if source.hours <= 0:
            self.db.delete(source)  # nothing left on that subtask that day; the hours live on the target row

    # -- reading -----------------------------------------------------------------------------

    def list(self, user: models.User, project_id: int) -> list[dict]:
        """Pending corrections first, then the most recent decided ones. An engineer sees their own."""
        project = self._project_for(user, project_id)
        correction = models.HoursCorrection
        query = self.db.query(correction).filter_by(project_id=project.id)
        if project_role(self.db, user, project.id) == ENGINEER:
            query = query.filter_by(employee_id=user.employee_id)
        pending = query.filter_by(status=PENDING).order_by(correction.id).all()
        decided = query.filter(correction.status != PENDING).order_by(correction.id.desc()).limit(RECENT).all()
        return self._outputs(user, project, [*pending, *decided])

    def _outputs(self, user: models.User, project: models.Project, corrections: list) -> list[dict]:
        """Rows for the page, with names and what this user may do (a fixed number of queries)."""
        if not corrections:
            return []
        task_ids = {c.from_task_id for c in corrections} | {c.to_task_id for c in corrections}
        tasks = {n.id: n for n in self.db.query(models.WbsNode).filter(models.WbsNode.id.in_(task_ids))}
        employee_ids = {c.employee_id for c in corrections}
        names = dict(
            self.db.query(models.Employee.id, models.Employee.name).filter(models.Employee.id.in_(employee_ids))
        )
        entry = models.TimeLogEntry
        sources = {
            (row.task_id, row.employee_id, row.work_date): row
            for row in self.db.query(entry).filter(
                entry.project_id == project.id,
                entry.task_id.in_({c.from_task_id for c in corrections}),
                entry.employee_id.in_(employee_ids),
            )
        }
        review = HoursReview(self.db, project, today_utc())

        def task_name(task_id: int, row: models.TimeLogEntry | None = None) -> str:
            task = tasks.get(task_id)
            if task is not None:
                return " ".join(filter(None, [task.wbs_code, task.task_name]))
            return (row.task_name if row is not None else None) or f"task #{task_id}"

        out = []
        for c in corrections:
            source = sources.get((c.from_task_id, c.employee_id, c.work_date))
            pending = c.status == PENDING
            out.append(
                {
                    "id": c.id,
                    "project_id": c.project_id,
                    "employee_id": c.employee_id,
                    "employee_name": names.get(c.employee_id, ""),
                    "work_date": c.work_date.isoformat(),
                    "from_task_id": c.from_task_id,
                    "from_task_name": task_name(c.from_task_id, source),
                    "to_task_id": c.to_task_id,
                    "to_task_name": task_name(c.to_task_id),
                    "hours": c.hours,
                    "note": c.note,
                    "status": c.status,
                    "requested_by": c.requested_by,
                    "created_at": c.created_at,
                    "decided_by": c.decided_by,
                    "decided_at": c.decided_at,
                    "decision_reason": c.decision_reason,
                    # What the reviewer needs to see before accepting hours: where they stand today.
                    "source_status": source.approval_status if source is not None else None,
                    "source_review_reason": source.review_reason if source is not None else None,
                    "can_decide": pending and review.may_review(user, tasks.get(c.to_task_id), c.employee_id),
                    "can_cancel": pending and user.employee_id is not None and c.employee_id == user.employee_id,
                }
            )
        return out

    # -- helpers -----------------------------------------------------------------------------

    def _project_for(self, user: models.User, project_id: int) -> models.Project:
        project = self.db.get(models.Project, project_id)
        if project is None:
            raise NotFoundError("Project not found.")
        if project_role(self.db, user, project.id) is None:
            raise ForbiddenError(NO_PROJECT_ACCESS)
        return project

    def _pending(self, correction_id: int) -> models.HoursCorrection:
        correction = self.db.get(models.HoursCorrection, correction_id)
        if correction is None:
            raise NotFoundError("Correction not found.")
        if correction.status != PENDING:
            raise ConflictError(ALREADY_DECIDED)
        return correction

    def _row(self, project_id: int, task_id: int, employee_id: int, day: date) -> models.TimeLogEntry | None:
        return (
            self.db.query(models.TimeLogEntry)
            .filter_by(project_id=project_id, task_id=task_id, employee_id=employee_id, work_date=day)
            .first()
        )
