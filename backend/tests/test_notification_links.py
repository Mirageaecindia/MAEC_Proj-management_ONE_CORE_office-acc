"""Every notification opens the page where its reader acts on it (app/services/notifications.link_for)."""

import models
from app.core.roles import Role
from app.services import notifications as notify


def _kinds():
    return {value for name, value in vars(notify).items() if name.isupper() and isinstance(value, str) and "_" in value}


def test_every_kind_of_notification_has_a_page_or_deliberately_none():
    kinds = _kinds() - {Role.BU_HEAD, Role.ENGINEER}
    missing = kinds - set(notify.LINKS) - notify.NO_LINK
    assert not missing, f"Add these to notifications.LINKS (or NO_LINK): {sorted(missing)}"


def test_the_page_depends_on_who_reads_it():
    def link(kind, role, project_id=7, own=None):
        return notify.link_for(
            models.Notification(notification_type=kind, recipient_role=role, project_id=project_id, link=own)
        )

    assert link(notify.RESOURCE_BOOKING_APPROVAL, Role.BU_HEAD) == "/resource-booking?projectId=7"
    assert link(notify.RESOURCE_BOOKING_REJECTED, Role.ENGINEER) == "/resource-booking?projectId=7"
    assert link(notify.EXECUTION_LOCKED, Role.BU_HEAD) == "/executive-dashboard?projectId=7"
    assert link(notify.EXECUTION_LOCKED, Role.ENGINEER) == "/engineer-performance-dashboard?projectId=7"
    assert link(notify.BU_HEAD_APPOINTED, Role.BU_HEAD, project_id=None) == "/created-projects"
    assert link(notify.PROJECT_ARCHIVED, Role.ENGINEER) is None  # nothing a lead can open
    own = "/weekly-logs?projectId=7&employeeId=2&weekStart=2026-10-05"
    assert link(notify.SUBTASK_DONE, Role.ENGINEER, own=own) == own


def test_a_submitted_booking_opens_resource_booking_for_the_bu_head(client, world):
    project_id = world.create_project()["id"]
    booking = {
        "employee_id": world.emp1.id,
        "utilization_rate": 50,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }
    client.post(f"/api/projects/{project_id}/resource-bookings", json=booking, headers=world.lead_h)
    client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h)

    notes = client.get("/api/notifications", headers=world.bu_h).json()

    pending = [n for n in notes if n["notification_type"] == notify.RESOURCE_BOOKING_APPROVAL]
    assert pending and pending[0]["link"] == f"/resource-booking?projectId={project_id}"
