"""Notifications: addressed to a role (e.g. every BU Head) or to specific users."""

from collections.abc import Iterable

from sqlalchemy.orm import Session

import models
from app.core.errors import ForbiddenError, NotFoundError
from app.core.roles import Role
from app.repositories.notifications import NotificationRepository

# Notification types
RESOURCE_BOOKING_APPROVAL = "resource_booking_approval"
RESOURCE_BOOKING_APPROVED = "resource_booking_approved"
RESOURCE_BOOKING_REJECTED = "resource_booking_rejected"
EXTENSION_REQUESTED = "extension_requested"
EXTENSION_DECIDED = "extension_decided"
THRESHOLD_WARNING = "threshold_warning"
EXECUTION_LOCKED = "execution_locked"
EXECUTION_RESUMED = "execution_resumed"


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


def notify_role(
    db: Session,
    role: str,
    notification_type: str,
    title: str,
    message: str,
    project_id: int | None = None,
    actor_name: str | None = None,
) -> models.Notification:
    """One notification visible to every user of `role`. Caller commits."""
    notification = models.Notification(
        recipient_role=role,
        notification_type=notification_type,
        title=title,
        message=message,
        project_id=project_id,
        actor_name=actor_name,
    )
    db.add(notification)
    db.flush()
    return notification


def notify_users(
    db: Session,
    user_ids: Iterable[int | None],
    role: str,
    notification_type: str,
    title: str,
    message: str,
    project_id: int | None = None,
    actor_name: str | None = None,
) -> None:
    """One notification per distinct user id (None ids are skipped). Caller commits."""
    for user_id in sorted({uid for uid in user_ids if uid}):
        db.add(
            models.Notification(
                recipient_role=role,
                recipient_user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                project_id=project_id,
                actor_name=actor_name,
            )
        )
    db.flush()


def project_lead_user_ids(project: models.Project) -> list[int]:
    """The real Lead accounts assigned to a project (Electrical, Mechanical, BIM)."""
    ids = (
        project.project_lead_electrical_user_id,
        project.project_lead_mechanical_user_id,
        project.project_lead_bim_user_id,
    )
    return [user_id for user_id in ids if user_id]


def notify_project_leads(
    db: Session, project: models.Project, notification_type: str, title: str, message: str, actor_name: str | None
) -> None:
    notify_users(
        db, project_lead_user_ids(project), Role.LEAD, notification_type, title, message, project.id, actor_name
    )


def create_bu_head_notification(
    db: Session,
    notification_type: str,
    title: str,
    message: str,
    project_id: int | None = None,
    actor_name: str | None = None,
) -> models.Notification:
    """Queue a notification for the BU Head (used by Lead code in main.py)."""
    return notify_role(db, Role.BU_HEAD, notification_type, title, message, project_id, actor_name)


def is_recipient(notification: models.Notification, user: models.User) -> bool:
    if notification.recipient_user_id is not None:
        return notification.recipient_user_id == user.id
    return notification.recipient_role == user.role


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
        if not is_recipient(notification, user):
            raise ForbiddenError("This notification is not for you.")
        notification.is_read = True
        self.db.commit()
