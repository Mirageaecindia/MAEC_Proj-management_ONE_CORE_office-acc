"""Timesheet arithmetic shared by every role's views and dashboards."""

import models

# Weekly totals are derived from Monday-Friday only. Automatic subtask
# tracking never writes Saturday/Sunday, so those columns always stay zero
# and never contribute to a week's total.
WEEKDAY_FIELDS = models.DAY_FIELDS[:5]


def entry_total(entry) -> float:
    """Total hours of one weekly timesheet row (Mon-Fri)."""
    return sum(float(getattr(entry, field) or 0) for field in WEEKDAY_FIELDS)


# Timesheet review states (TimeLogEntry.approval_status, WeeklyHoursSubmission.status).
APPROVED = "approved"
PENDING_REVIEW = "pending_review"
REJECTED = "rejected"


def effective_status(entry_status: str | None, week_status: str | None) -> str:
    """Review state of a timesheet row, combining the two Lead approval routes:
    approving the row itself, or approving the engineer's whole week
    (WeeklyHoursSubmission). A row approval wins; otherwise the week decides."""
    if entry_status == APPROVED or week_status == APPROVED:
        return APPROVED
    if week_status == REJECTED:
        return REJECTED
    return entry_status or PENDING_REVIEW
