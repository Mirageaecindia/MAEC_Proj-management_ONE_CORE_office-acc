from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

import models
from app.api.deps import get_booking_approval_service, get_notification_service
from app.core.security import get_current_user, require_any_role, require_bu_head, require_lead_or_bu_head
from app.services.booking_approval import BookingApprovalService
from app.services.notifications import NotificationService

router = APIRouter(tags=["resourcing"])


class BookingRejectRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_given(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the Lead a reason for the rejection.")
        return value.strip()


@router.get("/projects/{project_id}/resource-summary")
def resource_summary(
    project_id: int,
    user: models.User = Depends(require_lead_or_bu_head),
    service: BookingApprovalService = Depends(get_booking_approval_service),
):
    return service.summary(user, project_id)


@router.post("/projects/{project_id}/resource-bookings/approve")
def approve_resource_bookings(
    project_id: int,
    _user: models.User = Depends(require_bu_head),
    service: BookingApprovalService = Depends(get_booking_approval_service),
):
    """Approve every booking of a project that the Lead submitted (grants engineers access)."""
    return service.approve(project_id)


@router.post("/projects/{project_id}/resource-bookings/reject")
def reject_resource_bookings(
    project_id: int,
    payload: BookingRejectRequest,
    _user: models.User = Depends(require_bu_head),
    service: BookingApprovalService = Depends(get_booking_approval_service),
):
    """Send a pending submission back to the Lead as draft, with the reason (required)."""
    return service.reject(project_id, payload.reason)


@router.get("/notifications")
def list_notifications(
    user: models.User = Depends(require_any_role),
    service: NotificationService = Depends(get_notification_service),
):
    return service.list_for(user)


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: models.User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    service.mark_read(user, notification_id)
    return {"ok": True}
