"""Capacity checks shared by Lead bookings (main.py) and BU Head lead assignments."""

from datetime import date

from sqlalchemy.orm import Session

from app.domain.allocation import CAPACITY_PCT, peak_allocation
from app.repositories.bookings import BookingRepository


def allocated_pct(
    db: Session, employee_id: int, start: date | None, end: date | None, exclude_booking_id: int | None = None
) -> int:
    """The person's busiest day between start and end, across all active projects."""
    spans = BookingRepository(db).spans_for(employee_id, start, end, exclude_booking_id)
    return peak_allocation(spans, start, end)


def over_capacity_message(
    db: Session,
    name: str,
    employee_id: int,
    requested: int,
    start: date | None,
    end: date | None,
    exclude_booking_id: int | None = None,
) -> str | None:
    """Why `requested`% for these dates would put the person above 100% on some day, or None."""
    current = allocated_pct(db, employee_id, start, end, exclude_booking_id)
    if current + requested <= CAPACITY_PCT:
        return None
    return (
        f"{name} is already allocated {current}% during those dates. "
        f"Only {max(0, CAPACITY_PCT - current)}% is left, so {requested}% can't be booked."
    )
