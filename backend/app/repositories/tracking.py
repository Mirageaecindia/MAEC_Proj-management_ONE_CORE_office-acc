"""Data access for subtask Login/Logout sessions."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models

ACTIVE, ENDED = "active", "ended"


class TrackingRepository:
    def __init__(self, db: Session):
        self.db = db

    def active_session(self, employee_id: int) -> models.TimeSession | None:
        return self.db.query(models.TimeSession).filter_by(employee_id=employee_id, status=ACTIVE).first()

    def banked_seconds(self, employee_id: int, day: date) -> int:
        """Seconds banked by the engineer's ended sessions that started on `day` (UTC), in one query."""
        start = datetime.combine(day, time.min, tzinfo=UTC)
        session = models.TimeSession
        total = (
            self.db.query(func.sum(session.active_seconds))
            .filter(
                session.employee_id == employee_id,
                session.status == ENDED,
                session.login_at >= start,
                session.login_at < start + timedelta(days=1),
            )
            .scalar()
        )
        return int(total or 0)

    def silent_sessions(self, before: datetime) -> list[models.TimeSession]:
        """Open sessions whose last heartbeat is older than `before`."""
        session = models.TimeSession
        return self.db.query(session).filter(session.status == ACTIVE, session.last_seen_at < before).all()

    def last_session(self, employee_id: int) -> models.TimeSession | None:
        """The engineer's most recent session, open or ended."""
        return (
            self.db.query(models.TimeSession)
            .filter_by(employee_id=employee_id)
            .order_by(models.TimeSession.login_at.desc(), models.TimeSession.id.desc())
            .first()
        )

    def node(self, node_id: int) -> models.WbsNode | None:
        return self.db.get(models.WbsNode, node_id)

    def project(self, project_id: int) -> models.Project | None:
        return self.db.get(models.Project, project_id)
