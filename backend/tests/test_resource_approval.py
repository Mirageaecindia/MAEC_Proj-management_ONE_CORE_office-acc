"""Characterization: the BU Head side of resource booking (review & approve)."""

import pytest

import models


@pytest.fixture
def booked_project(client, world):
    """A project with one draft booking created by its Lead."""
    project_id = world.create_project()["id"]
    booking = {
        "employee_id": world.emp1.id,
        "planned_hours": 80,
        "utilization_rate": 50,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }
    response = client.post(f"/api/projects/{project_id}/resource-bookings", json=booking, headers=world.lead_h)
    assert response.status_code == 200, response.text
    return project_id, response.json()


def _submit(client, world, project_id):
    response = client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h)
    assert response.status_code == 200, response.text


def test_bu_head_sees_bookings_and_summary(client, world, booked_project):
    project_id, booking = booked_project

    bookings = client.get(f"/api/projects/{project_id}/resource-bookings", headers=world.bu_h).json()
    summary = client.get(f"/api/projects/{project_id}/resource-summary", headers=world.bu_h).json()

    assert [b["employee_name"] for b in bookings] == ["Arjun Mehta"]
    assert bookings[0]["approval_status"] == "draft"
    # Planned hours are derived server-side from the date range: weekdays x 8
    # (1-30 Sep 2026 = 22 weekdays = 176h); the client-sent 80 is ignored.
    # The 50% utilisation is not applied to the figure.
    assert bookings[0]["planned_hours"] == 176
    assert summary["total_booked_hours"] == 176
    assert summary["approval_status"] == "draft"
    assert summary["approval_status_label"] == "Draft"


def test_resource_summary_commercial_figures_are_placeholders(client, world, booked_project):
    # KNOWN (roadmap 7.4): commercial figures are hardcoded, not computed.
    project_id, _ = booked_project

    summary = client.get(f"/api/projects/{project_id}/resource-summary", headers=world.bu_h).json()

    assert summary["target_baseline_hours"] == 0
    assert summary["allocated_pct"] == 0
    assert summary["planned_labor_cost"] == 0
    assert summary["contract_value"] == 0
    assert summary["contract_currency"] == "USD"


def test_approval_workflow_draft_to_pending_to_approved(client, world, booked_project):
    project_id, _ = booked_project
    approve_url = f"/api/projects/{project_id}/resource-bookings/approve"

    assert client.post(approve_url, headers=world.bu_h).status_code == 409  # still draft

    _submit(client, world, project_id)
    notifications = client.get("/api/notifications", headers=world.bu_h).json()
    assert len(notifications) == 1
    assert notifications[0]["notification_type"] == "resource_booking_approval"
    assert notifications[0]["project_id"] == project_id
    assert notifications[0]["is_read"] is False
    assert notifications[0]["actor_name"] == "Anita Kumar"

    response = client.post(approve_url, headers=world.bu_h)
    assert response.status_code == 200
    assert response.json() == {"status": "approved", "status_label": "Approved"}

    bookings = client.get(f"/api/projects/{project_id}/resource-bookings", headers=world.bu_h).json()
    assert bookings[0]["approval_status"] == "approved"
    assert bookings[0]["approved_at"] is not None
    assert client.get("/api/notifications", headers=world.bu_h).json()[0]["is_read"] is True
    assert client.post(approve_url, headers=world.bu_h).status_code == 409  # already approved


def test_approve_requires_bookings_and_bu_head_role(client, world, booked_project):
    empty_project_id = world.create_project()["id"]
    project_id, _ = booked_project
    _submit(client, world, project_id)

    empty = client.post(f"/api/projects/{empty_project_id}/resource-bookings/approve", headers=world.bu_h)
    by_lead = client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.lead_h)

    assert empty.status_code == 400
    assert by_lead.status_code == 403


def test_editing_an_approved_booking_keeps_it_approved(client, world, booked_project):
    # KNOWN (roadmap 7.2): changes after approval do not reset the approval.
    project_id, booking = booked_project
    _submit(client, world, project_id)
    client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h)

    response = client.put(
        f"/api/projects/{project_id}/resource-bookings/{booking['id']}",
        json={"utilization_rate": 80},
        headers=world.lead_h,
    )

    assert response.status_code == 200
    assert response.json()["utilization_rate"] == 80
    assert response.json()["approval_status"] == "approved"


def test_bu_head_has_no_reject_action(client, world, booked_project):
    # KNOWN (roadmap 7.1): there is no reject / send-back endpoint yet.
    project_id, _ = booked_project

    response = client.post(f"/api/projects/{project_id}/resource-bookings/reject", headers=world.bu_h)

    assert response.status_code in (404, 405)


def test_notifications_can_only_be_marked_read_by_their_recipient(client, db, world, booked_project):
    project_id, _ = booked_project
    _submit(client, world, project_id)
    notification_id = db.query(models.Notification).one().id

    assert client.post(f"/api/notifications/{notification_id}/read", headers=world.eng_h).status_code == 403
    assert client.post(f"/api/notifications/{notification_id}/read", headers=world.bu_h).status_code == 200
    assert client.post("/api/notifications/999999/read", headers=world.bu_h).status_code == 404


def test_assignment_gantt_lists_booked_engineers(client, world, booked_project):
    project_id, booking = booked_project

    body = client.get("/api/resource-bookings/gantt", headers=world.bu_h).json()

    assert body["count"] == 1
    engineer = body["engineers"][0]
    assert engineer["name"] == "Arjun Mehta"
    assert engineer["total_allocation_pct"] == 50
    assignment = engineer["assignments"][0]
    assert assignment["booking_id"] == booking["id"]
    assert assignment["project_id"] == project_id
    assert assignment["start_date"] == "2026-09-01"
    assert assignment["end_date"] == "2026-09-30"
    assert assignment["has_date_range"] is True
