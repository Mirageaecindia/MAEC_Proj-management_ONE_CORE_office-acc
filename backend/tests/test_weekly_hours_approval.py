"""Characterization: the Weekly Hours submission/approval workflow.

The engineer submits a week (creating a WeeklyHoursSubmission row the Weekly
Hours section keys off of), and a lead may approve/reject ONLY a week whose
status is exactly 'submitted' — enforced server-side, not just in the UI.
Engineers can resubmit a rejected week, but never an approved one.
"""

from datetime import date

import pytest

WEEK = date(2026, 9, 7)
WEEK2 = date(2026, 9, 14)


@pytest.fixture
def approved(client, make, world):
    project_id = world.create_project()["id"]
    # The engineer must be booked and the booking APPROVED before they can log
    # or submit hours (access is only granted by BU Head approval).
    booking = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={
            "employee_id": world.emp1.id,
            "planned_hours": 100,
            "utilization_rate": 50,
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        headers=world.lead_h,
    )
    assert booking.status_code == 200, booking.text
    assert (
        client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    )
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=40)
    entry = make.time_entry(project_id, node, world.emp1, 8)
    return project_id, node, entry


def _submissions(client, headers, project_id, week=WEEK):
    return client.get(
        f"/api/projects/{project_id}/weekly-hours-submissions",
        params={"week_start": week.isoformat()},
        headers=headers,
    )


def _submit(client, headers, project_id, week=WEEK):
    return client.post(
        f"/api/projects/{project_id}/weekly-hours/submit",
        json={"week_start_date": week.isoformat()},
        headers=headers,
    )


def _review(client, headers, project_id, action, employee_id, week=WEEK):
    return client.post(
        f"/api/projects/{project_id}/weekly-hours/{action}",
        json={"week_start_date": week.isoformat(), "employee_id": employee_id},
        headers=headers,
    )


def test_no_submission_rows_until_engineer_submits(client, world, approved):
    project_id, *_ = approved
    assert _submissions(client, world.eng_h, project_id).json() == []
    assert _submissions(client, world.lead_h, project_id).json() == []
    assert _submissions(client, world.bu_h, project_id).json() == []


def test_engineer_submits_week_and_lead_approves(client, world, approved):
    project_id, _, _ = approved

    submitted = _submit(client, world.eng_h, project_id)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["employee_id"] == world.emp1.id
    assert body["week_start_date"] == WEEK.isoformat()
    assert body["status"] == "submitted"
    assert body["status_label"] == "Submitted for Approval"
    assert body["reviewed_by"] is None

    assert [s["status"] for s in _submissions(client, world.eng_h, project_id).json()] == ["submitted"]
    assert [s["status"] for s in _submissions(client, world.lead_h, project_id).json()] == ["submitted"]

    row = _review(client, world.lead_h, project_id, "approve", world.emp1.id)
    assert row.status_code == 200, row.text
    body = row.json()
    assert body["status"] == "approved"
    assert body["status_label"] == "Approved"
    assert body["reviewed_by"] == "Anita Kumar"
    assert body["reviewed_at"] is not None

    # An approved week can never be resubmitted by the engineer.
    assert _submit(client, world.eng_h, project_id).status_code == 409


def test_engineer_cannot_submit_a_week_without_logged_hours(client, make, world, approved):
    project_id, node, _ = approved
    response = _submit(client, world.eng_h, project_id, week=WEEK2)
    assert response.status_code == 409, response.text
    assert "no logged hours" in response.json()["detail"]
    assert _submissions(client, world.eng_h, project_id, week=WEEK2).json() == []

    # Once real hours exist for that week it becomes submittable.
    make.time_entry(project_id, node, world.emp1, 5, week=WEEK2)
    assert _submit(client, world.eng_h, project_id, week=WEEK2).status_code == 200


def test_rejected_week_can_be_resubmitted(client, make, world, approved):
    project_id, node, _ = approved
    make.time_entry(project_id, node, world.emp1, 5, week=WEEK2)

    assert _submit(client, world.eng_h, project_id, week=WEEK2).status_code == 200
    rejected = _review(client, world.lead_h, project_id, "reject", world.emp1.id, week=WEEK2)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reviewed_by"] == "Anita Kumar"

    resubmit = _submit(client, world.eng_h, project_id, week=WEEK2)
    assert resubmit.status_code == 200, resubmit.text
    assert resubmit.json()["status"] == "submitted"
    assert resubmit.json()["reviewed_by"] is None


def test_lead_cannot_review_unsubmitted_or_approved_weeks(client, world, approved):
    project_id, _, _ = approved
    assert _review(client, world.lead_h, project_id, "approve", world.emp1.id).status_code == 409
    assert _review(client, world.lead_h, project_id, "reject", world.emp1.id).status_code == 409

    _submit(client, world.eng_h, project_id)
    _review(client, world.lead_h, project_id, "approve", world.emp1.id)
    assert _review(client, world.lead_h, project_id, "reject", world.emp1.id).status_code == 409


def test_role_gates_on_submission_endpoints(client, world, approved):
    project_id, *_ = approved
    assert _submit(client, world.lead_h, project_id).status_code == 403
    assert _submit(client, world.bu_h, project_id).status_code == 403
    assert _review(client, world.eng_h, project_id, "approve", world.emp1.id, week=WEEK2).status_code == 403
    assert _review(client, world.eng_h, project_id, "reject", world.emp1.id, week=WEEK2).status_code == 403


def test_submission_payload_cannot_target_another_engineer(client, make, world, approved):
    project_id, _, _ = approved
    eng2 = make.user("eng.ravi", "engineer", "Ravi Kumar", employee_id=world.emp2.id)
    response = client.post(
        f"/api/projects/{project_id}/weekly-hours/submit",
        json={"week_start_date": WEEK.isoformat(), "employee_id": world.emp2.id},
        headers=world.eng_h,
    )
    assert response.status_code == 200, response.text
    assert response.json()["employee_id"] == world.emp1.id


def test_engineer_only_sees_their_own_submission(client, make, world, approved):
    project_id, _, _ = approved
    eng2 = make.user("eng.ravi", "engineer", "Ravi Kumar", employee_id=world.emp2.id)
    eng2_h = make.headers(eng2)
    booking = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={
            "employee_id": world.emp2.id,
            "planned_hours": 80,
            "utilization_rate": 40,
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        headers=world.lead_h,
    )
    assert booking.status_code == 200, booking.text
    assert (
        client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    )
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200

    _submit(client, world.eng_h, project_id)
    assert [s["employee_id"] for s in _submissions(client, world.eng_h, project_id).json()] == [world.emp1.id]
    assert _submissions(client, eng2_h, project_id).json() == []


def test_lead_cannot_review_hours_outside_their_scope(client, make, world, approved):
    project_id, _, _ = approved
    _submit(client, world.eng_h, project_id)

    # lead_m is a project lead (mechanical) but is not the WBS node's lead, so
    # emp1's hours are outside their scope.
    lead_m_h = make.headers(world.lead_m)
    response = _review(client, lead_m_h, project_id, "approve", world.emp1.id)
    assert response.status_code == 403, response.text

    # An unassigned lead cannot even reach the review step.
    assert _review(client, world.other_lead_h, project_id, "approve", world.emp1.id).status_code == 403


def test_bu_head_can_read_submission_status(client, world, approved):
    project_id, _, _ = approved
    _submit(client, world.eng_h, project_id)
    rows = _submissions(client, world.bu_h, project_id).json()
    assert [(s["employee_id"], s["status"]) for s in rows] == [(world.emp1.id, "submitted")]