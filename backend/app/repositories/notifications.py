from sqlalchemy.orm import Session

import models


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def recent_for(self, user: models.User, limit: int = 50) -> list[models.Notification]:
        """Notifications for this user, newest first: those addressed to them
        personally, plus role-wide ones (no recipient user) for their role."""
        N = models.Notification
        return (
            self.db.query(N)
            .filter(
                (N.recipient_user_id == user.id) | (N.recipient_user_id.is_(None) & (N.recipient_role == user.role))
            )
            .order_by(N.created_at.desc(), N.id.desc())
            .limit(limit)
            .all()
        )

    def get(self, notification_id: int) -> models.Notification | None:
        return self.db.get(models.Notification, notification_id)

    def unread(self, recipient_role: str, notification_type: str, project_id: int) -> list[models.Notification]:
        return (
            self.db.query(models.Notification)
            .filter_by(
                recipient_role=recipient_role,
                notification_type=notification_type,
                project_id=project_id,
                is_read=False,
            )
            .all()
        )

    def add(self, notification: models.Notification) -> None:
        self.db.add(notification)
