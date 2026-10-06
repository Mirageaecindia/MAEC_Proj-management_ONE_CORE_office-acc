"""BU Head side of resource booking: the project summary and approval.

Creating, editing and submitting bookings is Lead functionality in main.py;
it reuses `booking_approval_status` and `BOOKING_APPROVAL_LABELS` from here.
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.roles import Role
from app.domain.allocation import CAPACITY_PCT, peak_allocation
from app.domain.governance import governance_baseline
from app.domain.timesheets import today_utc
from app.repositories.bookings import BookingRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.projects import ProjectRepository
from app.repositories.users import UserRepository
from app.services import notifications as notify
from app.services.access import require_project_lead
from app.services.notifications import RESOURCE_BOOKING_APPROVAL

DRAFT, PENDING_APPROVAL, APPROVED = "draft", "pending_approval", "approved"

BOOKING_APPROVAL_LABELS = {
    DRAFT: "Draft",
    PENDING_APPROVAL: "Pending Approval",
    APPROVED: "Approved",
}

PROJECT_NOT_FOUND = "Project not found."


def overall_approval_status(statuses: Iterable[str]) -> str:
    """Project-level approval state derived from its bookings' states."""
    statuses = set(statuses)
    if not statuses:
        return DRAFT
    if statuses == {APPROVED}:
        return APPROVED
    if PENDING_APPROVAL in statuses:
        return PENDING_APPROVAL
    return DRAFT


def booking_approval_status(db: Session, project_id: int) -> str:
    """Function form kept for the Lead booking-submit code in main.py."""
    return overall_approval_status(BookingRepository(db).approval_statuses(project_id))


class BookingApprovalService:
    def __init__(
        self,
        db: Session,
        projects: ProjectRepository,
        bookings: BookingRepository,
        notifications: NotificationRepository,
        users: UserRepository,
    ):
        self.db = db
        self.projects = projects
        self.bookings = bookings
        self.notifications = notifications
        self.users = users

    def summary(self, user: models.User, project_id: int) -> dict:
        project = self._project(project_id)
        if user.role != Role.BU_HEAD:
            require_project_lead(self.db, user, project_id)
        status = overall_approval_status(self.bookings.approval_statuses(project_id))
        baseline = governance_baseline(project.target_effort_hours, project.extension_approved_hours)
        booked = self.bookings.planned_hours_total(project_id)  # engineers and leads, as on the roster
        return {
            "target_baseline_hours": baseline,  # target effort + approved extensions
            "extension_hours": float(project.extension_approved_hours or 0),
            "total_booked_hours": booked,
            "allocated_pct": round(booked / baseline * 100) if baseline > 0 else None,
            # No hourly rates exist yet (TODO N6): no cost rather than a made-up one.
            "planned_labor_cost": None,
            "contract_currency": project.contract_currency or "USD",
            "contract_value": float(project.contract_value or 0),
            "available_bench_engineers": self._bench_count(),
            "project_name": project.project_name,
            "approval_status": status,
            "approval_status_label": BOOKING_APPROVAL_LABELS.get(status),
        }

    def _bench_count(self) -> int:
        """Bookable people with free capacity today: under 100% across all active projects."""
        today = today_utc()
        spans = self.bookings.spans_by_employee(self.users.staff_employee_ids())
        return sum(
            1 for employee_spans in spans.values() if peak_allocation(employee_spans, today, today) < CAPACITY_PCT
        )

    def approve(self, project_id: int) -> dict:
        """Approve the Lead's submission. Approval is what grants engineers project access."""
        project, bookings = self._pending_submission(project_id)
        now = datetime.now(UTC)
        for booking in bookings:
            booking.approval_status = APPROVED
            booking.approved_at = now
        return self._close_submission(project, APPROVED)

    def reject(self, project_id: int, reason: str) -> dict:
        """Send the Lead's submission back to draft, with the reason, so it can be adjusted and re-submitted."""
        project, bookings = self._pending_submission(project_id)
        for booking in bookings:
            booking.approval_status = DRAFT
            booking.submitted_at = None
        return {**self._close_submission(project, DRAFT, reason), "reason": reason}

    def _pending_submission(self, project_id: int) -> tuple[models.Project, list[models.ResourceBooking]]:
        project = self._project(project_id)
        bookings = self.bookings.for_project(project_id)
        if not bookings:
            raise BadRequestError("No resource bookings have been assigned.")
        current = overall_approval_status(b.approval_status for b in bookings)
        if current == APPROVED:
            raise ConflictError("This resource booking has already been approved.")
        if current != PENDING_APPROVAL:
            raise ConflictError("This resource booking is not pending approval.")
        return project, bookings

    def _close_submission(self, project: models.Project, status: str, reason: str | None = None) -> dict:
        """The BU Head has decided: clear the pending notification and tell the project's Leads."""
        for notification in self.notifications.unread(Role.BU_HEAD, RESOURCE_BOOKING_APPROVAL, project.id):
            notification.is_read = True
        approved = status == APPROVED
        notify.notify_project_leads(
            self.db,
            project,
            notify.RESOURCE_BOOKING_APPROVED if approved else notify.RESOURCE_BOOKING_REJECTED,
            "Resource booking approved" if approved else "Resource booking returned to draft",
            f"The BU Head {'approved' if approved else 'rejected'} the resource booking for '{project.project_name}'."
            + ("" if approved else f" Reason: {reason} Adjust it and submit again."),
            "BU Head",
        )
        self.db.commit()
        return {"status": status, "status_label": BOOKING_APPROVAL_LABELS[status]}

    def _project(self, project_id: int) -> models.Project:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        return project
