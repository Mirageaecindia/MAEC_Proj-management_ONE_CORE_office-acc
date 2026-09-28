from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from app.domain.allocation import Span


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def for_project(self, project_id: int) -> list[models.ResourceBooking]:
        return self.db.query(models.ResourceBooking).filter_by(project_id=project_id).all()

    def approval_statuses(self, project_id: int) -> list[str]:
        rows = self.db.query(models.ResourceBooking.approval_status).filter_by(project_id=project_id).all()
        return [status for (status,) in rows]

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
