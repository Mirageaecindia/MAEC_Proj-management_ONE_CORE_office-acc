"""Characterization: the BU Head's read-only oversight of WBS, tasks and timesheets,
plus the Lead/Engineer actions the BU Head must NOT be able to perform."""

import pytest


@pytest.fixture
def tracked(make, world):
    project_id = world.create_project()["id"]
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, deliverable_status="In-Progress")
    entry = make.time_entry(project_id, node, world.emp1, 8)
    return project_id, node, entry


def test_bu_head_sees_full_wbs(client, world, tracked):
    project_id, node, _ = tracked

    rows = client.get(f"/api/projects/{project_id}/wbs-structure", headers=world.bu_h).json()

    assert [(r["id"], r["assigned_engineer_name"], r["level"]) for r in rows] == [(node.id, "Arjun Mehta", 1)]


def test_bu_head_can_open_task_details(client, world, tracked):
    _, node, _ = tracked

    response = client.get(f"/api/wbs-nodes/{node.id}", headers=world.bu_h)

    assert response.status_code == 200
    assert response.json()["node_type"] == "task"
    assert response.json()["deliverable_status"] == "In-Progress"


def test_bu_head_timeline_and_timesheet_views(client, world, tracked):
    project_id, node, _ = tracked

    timeline = client.get(f"/api/projects/{project_id}/timeline-logs", headers=world.bu_h).json()
    this_week = client.get(f"/api/projects/{project_id}/timesheet?week_start=2026-09-07", headers=world.bu_h).json()
    other_week = client.get(f"/api/projects/{project_id}/timesheet?week_start=2026-09-14", headers=world.bu_h).json()

    assert timeline["scope"]["role"] == "bu_head"
    assert [t["id"] for t in timeline["tasks"]] == [node.id]
    assert timeline["summary"]["total_hours_logged"] == 8.0
    assert [(e["employee_name"], e["total_hours"]) for e in this_week] == [("Arjun Mehta", 8.0)]
    assert other_week == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/projects/{project_id}/wbs-nodes", {"task_name": "x", "phase": "Space Planning"}),
        ("put", "/api/wbs-nodes/{node_id}", {"task_name": "x"}),
        ("delete", "/api/wbs-nodes/{node_id}", None),
        ("post", "/api/wbs-nodes/{node_id}/advance-status", {"new_status": "Submitted for Approval"}),
        ("post", "/api/wbs-nodes/{node_id}/approve", {"new_status": "Approved"}),
        ("post", "/api/wbs-nodes/{node_id}/comments", {"comment": "hi"}),
        ("post", "/api/subtask-tracking/start", {"subtask_id": 0}),
        ("post", "/api/subtask-tracking/logout", None),
        ("post", "/api/time-log-entries/{entry_id}/approve", None),
        ("post", "/api/time-log-entries/{entry_id}/reject", None),
        ("post", "/api/projects/{project_id}/resource-bookings", {"employee_id": 1}),
        ("post", "/api/projects/{project_id}/resource-bookings/submit", None),
        ("post", "/api/projects/{project_id}/extension-requests", {"requested_hours": 5}),
        ("post", "/api/projects/{project_id}/weekly-hours/submit", {"week_start_date": "2026-09-07"}),
        (
            "post",
            "/api/projects/{project_id}/weekly-hours/approve",
            {"week_start_date": "2026-09-07", "employee_id": 1},
        ),
        ("post", "/api/projects/{project_id}/weekly-hours/reject", {"week_start_date": "2026-09-07", "employee_id": 1}),
    ],
)
def test_bu_head_cannot_perform_lead_or_engineer_actions(client, world, tracked, method, path, body):
    project_id, node, entry = tracked
    url = path.format(project_id=project_id, node_id=node.id, entry_id=entry.id)

    kwargs = {"headers": world.bu_h}
    if body is not None:
        kwargs["json"] = body
    response = getattr(client, method)(url, **kwargs)

    assert response.status_code == 403, response.text


def test_bu_head_cannot_open_engineer_dashboards(client, world):
    assert client.get("/api/engineer-performance-dashboard", headers=world.bu_h).status_code == 403
    assert client.get("/api/engineer-performance", headers=world.bu_h).status_code == 403


def test_public_utility_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert set(client.get("/api/server-date").json()) == {"date", "datetime", "timezone"}
