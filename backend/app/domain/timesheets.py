"""Timesheet arithmetic and review states shared by every role's views and dashboards.

Hours are stored per day: one TimeLogEntry per subtask, engineer and date,
banked by Logout (decided 2026-09-28: approval is daily, the week is only the
sum of its days). All seven weekdays count: offices work different weeks.
"""

from collections.abc import Iterable
from datetime import date, timedelta

import models

# Review states of a day's hours (TimeLogEntry.approval_status).
APPROVED = "approved"
PENDING_REVIEW = "pending_review"
REJECTED = "rejected"

REASON_REQUIRED = "Give a reason for rejecting hours that were already approved."
NEVER_RE_APPROVED = "Rejected hours can't be approved again. The engineer corrects them instead."


def total_hours(entries: Iterable[models.TimeLogEntry], status: str | None = None) -> float:
    """The one totals function: the entries' hours (all, or only those in `status`)."""
    return round(sum(entry.hours or 0 for entry in entries if status is None or entry.approval_status == status), 2)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def reviewable(day: date, today: date) -> bool:
    """Only a finished day is reviewed (yesterday or earlier), so approved hours never change
    under a later Logout on the same day."""
    return day < today


def review_transition(current: str, new: str, reason: str | None) -> str | None:
    """Why a day's hours can't go from `current` to `new`, or None when they can.

    pending -> approved or rejected: normal. approved -> rejected: only with a reason (it is
    audited and shown to the BU Head). rejected -> approved: never; the hours are corrected
    instead, which keeps a rejection from being quietly undone."""
    if current == new:
        return f"These hours are already {new}."
    if current == REJECTED:
        return NEVER_RE_APPROVED
    if current == APPROVED and not (reason or "").strip():
        return REASON_REQUIRED
    return None
