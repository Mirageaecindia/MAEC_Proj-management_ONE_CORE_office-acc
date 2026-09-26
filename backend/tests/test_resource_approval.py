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


def test_only_a_lead_allocated_to_the_project_can_submit_bookings(client, world, booked_project):
    project_id, _ = booked_project

    unassigned = client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.other_lead_h)

    assert unassigned.status_code == 403
    summary = client.get(f"/api/projects/{project_id}/resource-summary", headers=world.bu_h).json()
    assert summary["approval_status"] == "draft"  # nothing was submitted to the BU Head
    _submit(client, world, project_id)  # the allocated lead can


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


def test_bu_head_can_reject_pending_submission_back_to_draft(client, db, world, booked_project):
    project_id, _ = booked_project
    reject_url = f"/api/projects/{project_id}/resource-bookings/reject"
    reason = {"reason": "Arjun is needed on Hotel Tower in September"}

    # a draft is not pending, so it cannot be rejected
    assert client.post(reject_url, json=reason, headers=world.bu_h).status_code == 409

    _submit(client, world, project_id)
    # the Lead must be told why (TODO C4)
    assert client.post(reject_url, json={"reason": "  "}, headers=world.bu_h).status_code == 422
    assert client.post(reject_url, headers=world.bu_h).status_code == 422
    rejected = client.post(reject_url, json=reason, headers=world.bu_h)
    assert rejected.status_code == 200
    assert rejected.json() == {"status": "draft", "status_label": "Draft", "reason": reason["reason"]}
    notice = (
        db.query(models.Notification)
        .filter_by(notification_type="resource_booking_rejected", recipient_user_id=world.lead_e.id)
        .one()
    )
    assert "Reason: Arjun is needed on Hotel Tower in September" in notice.message

    bookings = client.get(f"/api/projects/{project_id}/resource-bookings", headers=world.bu_h).json()
    assert bookings[0]["approval_status"] == "draft"

    # the Lead can adjust and re-submit after a rejection
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    # only a BU Head can reject, and only while pending
    assert client.post(reject_url, json=reason, headers=world.lead_h).status_code == 403
    assert client.post(reject_url, json=reason, headers=world.bu_h).status_code == 200


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


# --- Engineer project access is gated on BU Head approval -----------------------------


@pytest.fixture
def assigned_project(db, make, client, world):
    """A project with a draft booking for emp1 and a WBS task assigned to emp1."""
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
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    return project_id, node


def _eng_list(client, world):
    return {p["id"] for p in client.get("/api/projects", headers=world.eng_h).json()}


def _eng_open(client, world, project_id):
    return client.get(f"/api/projects/{project_id}", headers=world.eng_h)


def _time_entry(client, world, project_id, node_id):
    return client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_id, "week_start_date": "2026-09-07", "mon_hours": 2},
        headers=world.eng_h,
    )


def test_engineer_has_no_project_access_while_draft(client, world, assigned_project):
    project_id, node = assigned_project

    assert _eng_list(client, world) == set()
    assert _eng_open(client, world, project_id).status_code == 403
    assert client.get(f"/api/projects/{project_id}/wbs-structure", headers=world.eng_h).status_code == 403
    assert client.get(f"/api/projects/{project_id}/timeline-logs", headers=world.eng_h).status_code == 403
    assert client.get(f"/api/wbs-nodes/{node.id}", headers=world.eng_h).status_code == 403
    assert _time_entry(client, world, project_id, node.id).status_code == 403
    body = client.get("/api/engineer-performance", headers=world.eng_h).json()
    assert body["projects"] == []


def test_engineer_still_has_no_access_while_pending_approval(client, world, assigned_project):
    project_id, node = assigned_project
    _submit(client, world, project_id)

    assert _eng_list(client, world) == set()
    assert _eng_open(client, world, project_id).status_code == 403
    assert _time_entry(client, world, project_id, node.id).status_code == 403
    assert client.get("/api/engineer-performance", headers=world.eng_h).json()["projects"] == []
    # the engineer's dashboard must not leak the project either
    dashboard = client.get("/api/engineer-performance-dashboard", headers=world.eng_h).json()
    assert dashboard["projects"] == [] and dashboard["summary"]["total_tasks"] == 0


def test_engineer_gains_project_access_only_after_approval(client, world, assigned_project):
    project_id, node = assigned_project
    _submit(client, world, project_id)
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200

    assert _eng_list(client, world) == {project_id}
    assert _eng_open(client, world, project_id).status_code == 200
    rows = client.get(f"/api/projects/{project_id}/wbs-structure", headers=world.eng_h).json()
    assert {row["id"] for row in rows} == {node.id}
    assert client.get(f"/api/wbs-nodes/{node.id}", headers=world.eng_h).status_code == 200
    assert _time_entry(client, world, project_id, node.id).status_code == 200
    assert (
        client.get("/api/engineer-performance", headers=world.eng_h).json()["projects"][0]["project_id"] == project_id
    )
    # with a project id the dashboard resolves instead of 403ing
    assert (
        client.get(f"/api/engineer-performance-dashboard?project_id={project_id}", headers=world.eng_h).status_code
        == 200
    )


def test_rejected_assignment_grants_no_project_access(client, world, assigned_project):
    project_id, node = assigned_project
    _submit(client, world, project_id)
    assert (
        client.post(
            f"/api/projects/{project_id}/resource-bookings/reject", json={"reason": "Not needed"}, headers=world.bu_h
        ).status_code
        == 200
    )

    assert _eng_list(client, world) == set()
    assert _eng_open(client, world, project_id).status_code == 403
    assert _time_entry(client, world, project_id, node.id).status_code == 403
