"""Timesheet arithmetic and review states shared by every role's views and dashboards.

Hours are stored per day: one TimeLogEntry per subtask, engineer and date,
banked by Logout (decided 2026-09-28: approval is daily, the week is only the
sum of its days). All seven weekdays count: offices work different weeks.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import models

# Review states of a day's hours (TimeLogEntry.approval_status).
APPROVED = "approved"
PENDING_REVIEW = "pending_review"
REJECTED = "rejected"

# Hours in a day past which the rest is overtime (decided 2026-09-30): banked in full,
# flagged for the reviewer, and never approved in bulk.
DAILY_MARK_HOURS = 8

REASON_REQUIRED = "Give a reason for rejecting hours that were already approved."
INDIVIDUAL_ONLY = (
    "Only days over 8 hours or with unattended time are waiting for you; those are approved day by day, not in bulk."
)
NEVER_RE_APPROVED = (
    "Rejected hours are approved again only from the project's Rejected hours list: by one of its leads or "
    "the BU Head, within 7 days, with a reason."
)
# A rejection can be put right for this long (app/services/rejected_hours.py); after that it is final.
REAPPROVAL_WINDOW = timedelta(days=7)


def total_hours(entries: Iterable[models.TimeLogEntry], status: str | None = None) -> float:
    """The one totals function: the entries' hours (all, or only those in `status`)."""
    return round(sum(entry.hours or 0 for entry in entries if status is None or entry.approval_status == status), 2)


def over_mark(entry: models.TimeLogEntry) -> bool:
    """More than a working day's hours on one day: the reviewer looks at it individually."""
    return (entry.hours or 0) > DAILY_MARK_HOURS


def open_time(start: datetime, end: datetime, events: Iterable[tuple[datetime, str, bool]]) -> timedelta:
    """How long between `start` and `end` a project was open, i.e. paused by nothing.
    `events` are (when, what paused it, pausing?) in time order, e.g. a lock and its release;
    ones before `start` only set the state it starts in."""
    paused: set[str] = set()
    total, cursor = timedelta(0), start
    for at, reason, pausing in events:
        at = min(max(at, start), end)
        if not paused:
            total += at - cursor
        cursor = at
        (paused.add if pausing else paused.discard)(reason)
    if not paused:
        total += end - cursor
    return total


def today_utc() -> date:
    """The current day as the rows know it: a session's hours go to the UTC date it started on,
    so "finished" is judged against the UTC date too (05:30 to 05:30 India time)."""
    return datetime.now(UTC).date()


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
