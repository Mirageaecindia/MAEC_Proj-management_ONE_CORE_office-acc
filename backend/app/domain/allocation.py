"""Capacity: nobody may be booked above 100% on any single day (TODO N12).

A booking (engineer or lead) holds `utilization_rate` percent of a person's
time on every day from its start to its end date. What matters is the busiest
day, not the sum of every overlapping booking: 50% in January plus 50% in
March never adds up to 100% on any day. A missing date leaves that side open.
"""

from collections.abc import Iterable
from datetime import date, timedelta

CAPACITY_PCT = 100

Span = tuple[date | None, date | None, int]  # start, end (inclusive), percent


def peak_allocation(bookings: Iterable[Span], start: date | None = None, end: date | None = None) -> int:
    """Highest daily total of the bookings on any day between start and end (inclusive)."""
    window_start, window_end = start or date.min, end or date.max
    changes: dict[date, int] = {}
    for booking_start, booking_end, pct in bookings:
        first = max(booking_start or date.min, window_start)
        last = min(booking_end or date.max, window_end)
        if first > last or not pct:
            continue
        changes[first] = changes.get(first, 0) + pct
        if last < date.max:
            changes[last + timedelta(days=1)] = changes.get(last + timedelta(days=1), 0) - pct
    peak = running = 0
    for day in sorted(changes):
        running += changes[day]
        peak = max(peak, running)
    return peak
