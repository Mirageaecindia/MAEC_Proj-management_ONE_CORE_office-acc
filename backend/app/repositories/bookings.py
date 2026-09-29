from collections.abc import Collection
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from app.domain.allocation import Span

ENGINEER, LEAD = "engineer", "lead"  # ResourceBooking.role


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def for_project(self, project_id: int, role: str = ENGINEER) -> list[models.ResourceBooking]:
        """A project's bookings of one role. The approval workflow concerns engineer bookings only."""
        return self.db.query(models.ResourceBooking).filter_by(project_id=project_id, role=role).all()

    def approval_statuses(self, project_id: int) -> list[str]:
        rows = (
            self.db.query(models.ResourceBooking.approval_status).filter_by(project_id=project_id, role=ENGINEER).all()
        )
        return [status for (status,) in rows]

    def lead_assignments(self, project_ids: Collection[int]) -> list[models.ResourceBooking]:
        return (
            self.db.query(models.ResourceBooking)
            .filter(models.ResourceBooking.project_id.in_(project_ids), models.ResourceBooking.role == LEAD)
            .all()
        )

    def delete_lead_assignments(self, project_id: int) -> None:
        for booking in self.for_project(project_id, LEAD):
            self.db.delete(booking)

    def spans_by_employee(self, employee_ids: Collection[int]) -> dict[int, list[Span]]:
        """employee id -> (start, end, %) of every booking on an active project, in one query."""
        booking = models.ResourceBooking
        rows = (
            self.db.query(booking.employee_id, booking.start_date, booking.end_date, booking.utilization_rate)
            .join(models.Project, models.Project.id == booking.project_id)
            .filter(booking.employee_id.in_(employee_ids), models.Project.archived_at.is_(None))
            .all()
        )
        spans: dict[int, list[Span]] = {employee_id: [] for employee_id in employee_ids}
        for employee_id, first, last, pct in rows:
            spans[employee_id].append((first, last, pct or 0))
        return spans

    def has_booking(self, project_id: int, employee_id: int, role: str) -> bool:
        return (
            self.db.query(models.ResourceBooking.id)
            .filter_by(project_id=project_id, employee_id=employee_id, role=role)
            .first()
            is not None
        )

    def spans_for(
        self, employee_id: int, start: date | None, end: date | None, exclude_booking_id: int | None = None
    ) -> list[Span]:
        """(start, end, %) of the person's bookings on active projects that overlap [start, end]."""
        booking = models.ResourceBooking
        query = (
            self.db.query(booking.start_date, booking.end_date, booking.utilization_rate)
            .join(models.Project, models.Project.id == booking.project_id)
            .filter(booking.employee_id == employee_id, models.Project.archived_at.is_(None))
        )
        if end is not None:
            query = query.filter(or_(booking.start_date.is_(None), booking.start_date <= end))
        if start is not None:
            query = query.filter(or_(booking.end_date.is_(None), booking.end_date >= start))
        if exclude_booking_id is not None:
            query = query.filter(booking.id != exclude_booking_id)
        return [(first, last, pct or 0) for first, last, pct in query.all()]
