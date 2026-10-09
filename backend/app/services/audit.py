"""The audit log (decided 2026-10-07): writing an entry for each change, reading it back, and
forgetting entries older than AUDIT_RETENTION_DAYS.

Entries are written by app/api/middleware.py after every successful change request, so
no feature has to remember to log. Each entry names the person, the item in words
("1.2 Risers", "Ravi Kumar on 2026-10-05") and the project, as they were at that moment.
Each person reads their own entries; the BU Head reads everyone's.
"""

import asyncio
import csv
import io
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from app.core.config import get_settings
from app.core.errors import ForbiddenError
from app.core.roles import Role
from app.domain.audit import CATALOG, FAILED_SIGN_IN, NOT_AUDITED, detail_from, sentence

log = logging.getLogger(__name__)

PURGE_INTERVAL = timedelta(hours=6)
PAGE_LIMIT = 200
EXPORT_LIMIT = 20_000
BU_HEAD_ONLY = "Only a BU Head sees everyone's activity."


def node_label(node: models.WbsNode | None) -> str | None:
    if node is None:
        return None
    return f"{node.wbs_code or ''} {node.task_name}".strip()


def person_label(user: models.User | None) -> str | None:
    return (user.full_name or user.username) if user is not None else None


@dataclass
class Before:
    """What only the request's start can tell: who is acting (a sign-out ends the session),
    and the subtask a Logout is about to close."""

    actor: models.User | None = None
    open_subtask: models.WbsNode | None = None


def before_request(db: Session, method: str, path: str, token: str | None) -> Before:
    actor = None
    if token:
        session = db.query(models.LoginSession).filter_by(token=token).first()
        actor = db.get(models.User, session.user_id) if session else None
    before = Before(actor=actor)
    if method == "POST" and path == "/api/subtask-tracking/logout" and actor and actor.employee_id:
        running = db.query(models.TimeSession).filter_by(employee_id=actor.employee_id, status="active").first()
        before.open_subtask = db.get(models.WbsNode, running.subtask_id) if running else None
    return before


def _user_by_username(db: Session, username) -> models.User | None:
    if not isinstance(username, str) or not username.strip():
        return None
    return db.query(models.User).filter(models.User.username.ilike(username.strip())).first()


def _target(db: Session, path_params: dict, body: dict, before: Before) -> tuple[str | None, int | None]:
    """The item the action was about, in words, and its project."""

    def number(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    project_id = number(path_params.get("project_id"))
    if (node_id := number(path_params.get("node_id"))) is not None:
        node = db.get(models.WbsNode, node_id)
        return node_label(node), node.project_id if node else project_id
    if (entry_id := number(path_params.get("entry_id"))) is not None:
        entry = db.get(models.TimeLogEntry, entry_id)
        if entry is None:
            return None, project_id
        employee = db.get(models.Employee, entry.employee_id)
        task = node_label(db.get(models.WbsNode, entry.task_id)) or entry.task_name
        who = employee.name if employee else "an engineer"
        return f"{who} on {entry.work_date.isoformat()} ({task})", entry.project_id
    if (user_id := number(path_params.get("user_id"))) is not None:
        return person_label(db.get(models.User, user_id)), project_id
    if phase := path_params.get("phase"):  # a phase blueprint, by its phase's name
        from app.services.wbs_blueprints import BLUEPRINTS

        return BLUEPRINTS.get(str(phase), (str(phase).replace("-", " "),))[0], project_id
    if (booking_id := number(path_params.get("booking_id"))) is not None:
        booking = db.get(models.ResourceBooking, booking_id)
        employee = db.get(models.Employee, booking.employee_id) if booking else None
        return (employee.name if employee else None), project_id
    if (subtask_id := number(body.get("subtask_id"))) is not None:
        node = db.get(models.WbsNode, subtask_id)
        return node_label(node), node.project_id if node else project_id
    if before.open_subtask is not None:
        return node_label(before.open_subtask), before.open_subtask.project_id
    if (employee_id := number(body.get("employee_id"))) is not None:
        employee = db.get(models.Employee, employee_id)
        return (employee.name if employee else None), project_id
    if "username" in body:
        return person_label(_user_by_username(db, body.get("username"))), project_id
    return None, project_id


def record(
    db: Session,
    *,
    method: str,
    template: str | None,
    route_name: str | None,
    path_params: dict,
    body: dict,
    status: int,
    before: Before,
    ip: str | None,
    now: datetime | None = None,
) -> models.AuditEvent | None:
    """Write the entry for one finished request, or nothing when it isn't one to keep."""
    key = (method, template)
    if template is None or key in NOT_AUDITED or key not in CATALOG:
        return None
    category, label = CATALOG[key]
    actor, summary, action = before.actor, None, route_name or "unknown"
    if template == "/api/auth/login":
        actor = _user_by_username(db, body.get("username"))
        if status == 401 and actor is not None:  # someone tried this account's password and failed
            summary, action = FAILED_SIGN_IN, "failed_sign_in"
        elif not 200 <= status < 300:
            return None
    elif not 200 <= status < 300:
        return None
    if actor is None:
        return None
    target, project_id = _target(db, path_params, body if template != "/api/auth/login" else {}, before)
    project = db.get(models.Project, project_id) if project_id is not None else None
    event = models.AuditEvent(
        at=now or datetime.now(UTC),
        user_id=actor.id,
        user_name=person_label(actor),
        user_role=actor.role,
        category=category,
        action=action[:60],
        summary=(summary or sentence(label, target, detail_from(body)))[:500],
        project_id=project.id if project else None,
        project_name=project.project_name if project else None,
        ip=(ip or None) and ip[:64],
    )
    db.add(event)
    db.commit()
    return event


def purge_old(db: Session, now: datetime, days: int) -> int:
    """Delete entries older than `days`. Returns how many went."""
    cutoff = now - timedelta(days=days)
    removed = db.query(models.AuditEvent).filter(models.AuditEvent.at < cutoff).delete(synchronize_session=False)
    db.commit()
    return removed


async def purge_forever(session_factory, interval: timedelta = PURGE_INTERVAL) -> None:
    """Background task started with the app: keep the log to its retention window."""
    while True:
        try:
            with session_factory() as db:
                removed = purge_old(db, datetime.now(UTC), get_settings().audit_retention_days)
            if removed:
                log.info("Audit log: %s entries past the retention window deleted", removed)
        except Exception:  # never let a failed purge stop the app; the next run tries again
            log.exception("Audit log purge failed")
        await asyncio.sleep(interval.total_seconds())


# -- reading --------------------------------------------------------------------------------


@dataclass
class AuditFilter:
    user_id: int | None = None
    project_id: int | None = None
    category: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    text: str | None = None
    limit: int = 50
    offset: int = 0


def event_output(event: models.AuditEvent) -> dict:
    return {
        "id": event.id,
        "at": event.at,
        "user_id": event.user_id,
        "user_name": event.user_name,
        "user_role": event.user_role,
        "category": event.category,
        "summary": event.summary,
        "project_id": event.project_id,
        "project_name": event.project_name,
    }


class AuditLog:
    def __init__(self, db: Session):
        self.db = db

    def mine(self, user: models.User, filters: AuditFilter) -> dict:
        """The person's own entries: the actions they took."""
        filters.user_id = user.id
        return self._page(filters)

    def everyone(self, user: models.User, filters: AuditFilter) -> dict:
        """Everyone's entries, BU Heads included (BU Head only)."""
        self._require_bu_head(user)
        return self._page(filters)

    def export_csv(self, user: models.User, filters: AuditFilter) -> str:
        self._require_bu_head(user)
        rows = self._query(filters).limit(EXPORT_LIMIT).all()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["When (UTC)", "Person", "Role", "Category", "Action", "Project"])
        for e in rows:
            writer.writerow([e.at.isoformat(), e.user_name, e.user_role, e.category, e.summary, e.project_name or ""])
        return out.getvalue()

    def _page(self, filters: AuditFilter) -> dict:
        query = self._query(filters)
        limit = max(1, min(filters.limit, PAGE_LIMIT))
        events = query.offset(max(0, filters.offset)).limit(limit).all()
        return {"events": [event_output(e) for e in events], "total": query.count()}

    def _query(self, filters: AuditFilter):
        event = models.AuditEvent
        query = self.db.query(event)
        if filters.user_id is not None:
            query = query.filter(event.user_id == filters.user_id)
        if filters.project_id is not None:
            query = query.filter(event.project_id == filters.project_id)
        if filters.category:
            query = query.filter(event.category == filters.category)
        if filters.date_from:
            query = query.filter(event.at >= datetime.combine(filters.date_from, time.min, tzinfo=UTC))
        if filters.date_to:
            query = query.filter(event.at < datetime.combine(filters.date_to + timedelta(days=1), time.min, tzinfo=UTC))
        if filters.text and filters.text.strip():
            needle = f"%{filters.text.strip()}%"
            query = query.filter(or_(event.summary.ilike(needle), event.user_name.ilike(needle)))
        return query.order_by(event.at.desc(), event.id.desc())

    @staticmethod
    def _require_bu_head(user: models.User) -> None:
        if user.role != Role.BU_HEAD:
            raise ForbiddenError(BU_HEAD_ONLY)
