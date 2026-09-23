"""Role-targeted notifications (today: booking approvals for the BU Head)."""

from sqlalchemy.orm import Session

import models
from app.core.errors import ForbiddenError, NotFoundError
from app.core.roles import Role
from app.repositories.notifications import NotificationRepository

RESOURCE_BOOKING_APPROVAL = "resource_booking_approval"


def notification_output(notification: models.Notification) -> dict:
    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "recipient_user_id": notification.recipient_user_id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "project_id": notification.project_id,
        "actor_name": notification.actor_name,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def create_bu_head_notification(
    db: Session,
    notification_type: str,
    title: str,
    message: str,
    project_id: int | None = None,
    actor_name: str | None = None,
) -> models.Notification:
    """Queue a notification for the BU Head (used by the Lead booking submit in main.py)."""
    notification = models.Notification(
        recipient_role=Role.BU_HEAD,
        notification_type=notification_type,
        title=title,
        message=message,
        project_id=project_id,
        actor_name=actor_name,
    )
    db.add(notification)
    db.flush()
    return notification


class NotificationService:
    def __init__(self, db: Session, notifications: NotificationRepository):
        self.db = db
        self.notifications = notifications

    def list_for(self, user: models.User) -> list[dict]:
        return [notification_output(n) for n in self.notifications.recent_for(user)]

    def mark_read(self, user: models.User, notification_id: int) -> None:
        notification = self.notifications.get(notification_id)
        if not notification:
            raise NotFoundError("Notification not found.")
        if notification.recipient_role != user.role and notification.recipient_user_id != user.id:
            raise ForbiddenError("This notification is not for you.")
        notification.is_read = True
        self.db.commit()
