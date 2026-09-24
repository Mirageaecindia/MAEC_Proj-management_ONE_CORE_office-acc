"""Characterization: Executive Dashboard figures and BU Head governance actions.

Reference scenario (see `governed`): two WBS nodes of 40h + 60h assigned to one
engineer whose discipline is "Mechanical Engineer"; 30h approved + 20h pending
logged. Contract 100,000 USD, threshold 80%, target effort 500h.
"""

from datetime import date

import pytest

import models


@pytest.fixture
def governed(client, make, world):
    project = world.create_project(
        total_contract_value=100000, alert_override_threshold_pct=80, target_effort_hours=500
    )
    project_id = project["id"]
    # The engineer must be booked and the booking APPROVED before they can log
    # hours (access is only granted by BU Head approval of the assignment).
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
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    node_a = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=40)
    node_b = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=60)
    make.time_entry(project_id, node_a, world.emp1, 30, status="approved")
    pending = make.time_entry(project_id, node_b, world.emp1, 20, status="pending_review")
    return project_id, node_a, node_b, pending


def _dashboard(client, headers, project_id):
    response = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Dashboard figures ---------------------------------------------------------------


def test_dashboard_figures_for_reference_scenario(client, world, governed):
    project_id, *_ = governed

    data = _dashboard(client, world.bu_h, project_id)

    assert data["summary"] == {
        "scheduled_hours": 100,
        "approved_hours": 30.0,
        "logged_hours": 50.0,
        "pending_hours": 20.0,
        "pending_entries": 1,
        "consumption_pct": 50.0,
    }
    assert data["commercial_budget_burn"] == {
        "currency": "USD",
        "total": 100000.0,
        "consumed": 50000.0,
        "remaining": 50000.0,
        "percent": 50.0,
    }
    assert data["spi"] == {"value": 0.3, "note": "Behind plan — 30 earned of 100 planned baseline hours."}
    assert data["governance_status"]["status"] == "normal"
    assert data["governance_status"]["max_discipline"] == "Mechanical Engineer"
    assert data["governance_status"]["soft_locked"] is False
    assert data["exceptions"] == []
    assert data["monthly_data"] == [
        {
            "month": "2026-09",
            "month_label": "Sep 2026",
            "planned_baseline": 100.0,
            "normal_consumption": 50.0,
            "exceeded_threshold": 0.0,
        }
    ]


def test_consumption_over_threshold_raises_discipline_exception(client, make, world, governed):
    project_id, _, node_b, _ = governed
    make.time_entry(project_id, node_b, world.emp1, 40, status="approved", week=date(2026, 9, 14))

    data = _dashboard(client, world.bu_h, project_id)

    assert data["governance_status"]["status"] == "exceeded"
    assert data["governance_status"]["max_discipline_pct"] == 90.0
    assert [e["discipline"] for e in data["exceptions"]] == ["Mechanical Engineer"]
    assert data["monthly_data"][0]["exceeded_threshold"] == 90.0
    assert data["monthly_data"][0]["normal_consumption"] == 0.0


def test_baseline_ignores_bu_head_target_effort_hours(client, world, governed):
    # KNOWN (roadmap 5.2): consumption is measured against the WBS estimate
    # total (100h), not the BU Head's 500h target effort baseline.
    project_id, *_ = governed

    data = _dashboard(client, world.bu_h, project_id)

    assert data["hours_consumption"]["scheduled"] == 100
    assert data["hours_consumption"]["percent"] == 50.0


def test_dashboard_access(client, world, governed):
    project_id, *_ = governed

    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.eng_h).status_code == 403
    assert client.get("/api/projects/999999/executive-dashboard", headers=world.bu_h).status_code == 404
    # KNOWN (hand-off to Lead developer): any lead can read any project's
    # commercial dashboard, including leads not assigned to the project.
    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.other_lead_h).status_code == 200


# --- Stop execution (soft lock) ---------------------------------------------------------


def test_stop_execution_requires_comment_and_bu_head(client, world, governed):
    project_id, *_ = governed
    url = f"/api/projects/{project_id}/governance/stop-execution"

    assert client.post(url, json={"comments": "   "}, headers=world.bu_h).status_code == 422
    assert client.post(url, json={"comments": "Halt"}, headers=world.lead_h).status_code == 403


def test_stop_execution_soft_locks_timesheets(client, db, world, governed):
    project_id, node_a, _, pending = governed

    response = client.post(
        f"/api/projects/{project_id}/governance/stop-execution", json={"comments": "Over budget"}, headers=world.bu_h
    )

    assert response.status_code == 200
    action = response.json()
    assert action["action"] == "stop_execution"
    assert action["discipline"] == "Mechanical Engineer"
    assert action["consumption_pct"] == 50.0
    assert action["threshold_pct"] == 80
    assert action["consumption_hours"] == 50.0
    assert action["comments"] == "Over budget"
    assert action["created_by"] == "Test BU Head"
    assert _dashboard(client, world.bu_h, project_id)["governance_status"]["soft_locked"] is True

    log_hours = client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_a.id, "week_start_date": "2026-09-21", "mon_hours": 2},
        headers=world.eng_h,
    )
    approve_hours = client.post(f"/api/time-log-entries/{pending.id}/approve", headers=world.lead_h)
    assert log_hours.status_code == 409
    assert approve_hours.status_code == 409


def test_stop_execution_is_not_idempotent_and_cannot_be_undone(client, db, world, governed):
    # KNOWN (roadmap 6.1): repeated stops each add an audit row, and there is
    # no resume endpoint.
    project_id, *_ = governed
    url = f"/api/projects/{project_id}/governance/stop-execution"

    client.post(url, json={"comments": "first"}, headers=world.bu_h)
    client.post(url, json={"comments": "second"}, headers=world.bu_h)

    assert db.query(models.GovernanceAction).filter_by(project_id=project_id, action="stop_execution").count() == 2
    resume = client.post(f"/api/projects/{project_id}/governance/resume-execution", json={}, headers=world.bu_h)
    assert resume.status_code in (404, 405)


# --- Extension requests -----------------------------------------------------------------


def _request_extension(client, headers, project_id, hours=40, justification="Scope creep"):
    return client.post(
        f"/api/projects/{project_id}/extension-requests",
        json={"requested_hours": hours, "justification": justification},
        headers=headers,
    )


def test_extension_request_appears_in_bu_head_queue(client, world, governed):
    project_id, *_ = governed

    created = _request_extension(client, world.lead_h, project_id)

    assert created.status_code == 201
    request = created.json()
    assert request["status"] == "pending"
    assert request["status_label"] == "Pending BU Head Approval"
    assert request["requested_by"] == "Anita Kumar"
    data = _dashboard(client, world.bu_h, project_id)
    assert data["current_extension_request"]["id"] == request["id"]
    assert data["project"]["extension_status"] == "pending"
    assert data["governance_actions"][0]["action"] == "extension_request"
    assert data["governance_actions"][0]["requested_hours"] == 40
    assert _request_extension(client, world.lead_h, project_id).status_code == 409  # one pending at a time
    assert _request_extension(client, world.lead_h, project_id, hours=0).status_code == 422


def test_approving_extension_records_hours_but_does_not_change_consumption(client, db, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    url = f"/api/projects/{project_id}/extension-requests/{request_id}/decision"

    response = client.post(url, json={"decision": "approve", "comments": "OK"}, headers=world.bu_h)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["decided_by"] == "Test BU Head"
    assert response.json()["decision_comments"] == "OK"
    project = db.get(models.Project, project_id)
    assert project.extension_status == "approved"
    assert project.extension_approved_hours == 40
    data = _dashboard(client, world.bu_h, project_id)
    assert data["current_extension_request"] is None
    assert [a["action"] for a in data["governance_actions"]] == ["approve_extension", "extension_request"]
    # KNOWN (roadmap 5.2 / 6.3): approved hours never reach the baseline.
    assert data["summary"]["consumption_pct"] == 50.0
    assert client.post(url, json={"decision": "approve"}, headers=world.bu_h).status_code == 409


def test_rejecting_extension(client, db, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
        json={"decision": "reject"},
        headers=world.bu_h,
    )

    assert response.json()["status"] == "rejected"
    project = db.get(models.Project, project_id)
    assert project.extension_status == "rejected"
    assert project.extension_approved_hours is None


def test_extension_decision_guards(client, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    url = f"/api/projects/{project_id}/extension-requests/{request_id}/decision"

    assert client.post(url, json={"decision": "maybe"}, headers=world.bu_h).status_code == 422
    assert client.post(url, json={"decision": "approve"}, headers=world.lead_h).status_code == 403
    missing = f"/api/projects/{project_id}/extension-requests/999999/decision"
    assert client.post(missing, json={"decision": "approve"}, headers=world.bu_h).status_code == 404


def test_unassigned_lead_can_file_extension_request(client, world, governed):
    # KNOWN (hand-off to Lead developer): no project-access check on requests.
    project_id, *_ = governed

    assert _request_extension(client, world.other_lead_h, project_id).status_code == 201


def test_legacy_extension_endpoints_still_decide_pending_request(client, world, governed):
    # Legacy duplicates of the decision endpoint (roadmap 1.6: remove).
    project_id, *_ = governed
    approve_url = f"/api/projects/{project_id}/governance/approve-extension"
    reject_url = f"/api/projects/{project_id}/governance/reject-extension"

    assert client.post(approve_url, json={"comments": "x"}, headers=world.bu_h).status_code == 409
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    approved = client.post(approve_url, json={"comments": "fine"}, headers=world.bu_h)
    assert approved.status_code == 200
    assert approved.json()["action"] == "approve_extension"
    assert approved.json()["extension_request_id"] == request_id

    second_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    rejected = client.post(reject_url, json={"comments": "no"}, headers=world.bu_h)
    assert rejected.json()["action"] == "reject_extension"
    assert rejected.json()["extension_request_id"] == second_id
