from sqlalchemy.orm import Session

import models


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def recent_for(self, user: models.User, limit: int = 50) -> list[models.Notification]:
        """Notifications addressed to the user's role or to the user directly, newest first."""
        return (
            self.db.query(models.Notification)
            .filter(
                (models.Notification.recipient_role == user.role) | (models.Notification.recipient_user_id == user.id)
            )
            .order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
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
