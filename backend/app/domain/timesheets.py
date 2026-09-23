"""Timesheet arithmetic shared by every role's views and dashboards."""

import models

# Weekly totals are derived from Monday-Friday only. Automatic subtask
# tracking never writes Saturday/Sunday, so those columns always stay zero
# and never contribute to a week's total.
WEEKDAY_FIELDS = models.DAY_FIELDS[:5]


def entry_total(entry) -> float:
    """Total hours of one weekly timesheet row (Mon-Fri)."""
    return sum(float(getattr(entry, field) or 0) for field in WEEKDAY_FIELDS)
