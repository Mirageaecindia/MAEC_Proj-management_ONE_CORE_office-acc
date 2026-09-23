"""Characterization: GET /api/projects/{id}/work-summary (BU Head only)."""

import pytest


@pytest.fixture
def summary_project(make, world):
    project_id = world.create_project()["id"]
    approved = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, deliverable_status="Approved")
    make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, deliverable_status="Completed", phase="STR Coordination"
    )
    in_progress = make.wbs_node(project_id, world.lead_e, engineer=world.emp2, deliverable_status="In-Progress")
    make.time_entry(project_id, approved, world.emp1, 10, status="approved")
    make.time_entry(project_id, in_progress, world.emp2, 5, status="pending_review")
    return project_id, approved


def _summary(client, world, project_id):
    response = client.get(f"/api/projects/{project_id}/work-summary", headers=world.bu_h)
    assert response.status_code == 200, response.text
    return response.json()


def test_summary_totals(client, world, summary_project):
    project_id, _ = summary_project

    body = _summary(client, world, project_id)

    assert body["summary"] == {
        "total_nodes": 3,
        # KNOWN (roadmap 5.3): only the legacy "Completed" status counts;
        # the current terminal statuses "Approved"/"Done" are ignored.
        "completed_nodes": 1,
        "scheduled_hours": 120,
        "approved_hours": 10.0,
        "logged_hours": 15.0,
        "pending_hours": 5.0,
        "pending_entries": 1,
    }
    assert body["phase_completion"] == {
        "Space Planning": {"total": 2, "completed": 0},
        "STR Coordination": {"total": 1, "completed": 1},
    }


def test_lead_oversight_rows(client, world, summary_project):
    project_id, _ = summary_project

    leads = _summary(client, world, project_id)["leads"]

    assert leads == [
        {
            "name": "Anita Kumar",
            "phases": ["STR Coordination", "Space Planning"],
            "nodes_managed": 3,
            "phase_completion": {
                "STR Coordination": {"total": 1, "completed": 1},
                "Space Planning": {"total": 2, "completed": 0},
            },
            "approved_hours": 10.0,
            "logged_hours": 15.0,
            "pending_approvals": 1,
        }
    ]


def test_engineer_contribution_rows(client, world, summary_project):
    project_id, approved = summary_project

    engineers = {e["name"]: e for e in _summary(client, world, project_id)["engineers"]}

    arjun = engineers["Arjun Mehta"]
    assert arjun["assigned_nodes"] == 2
    assert arjun["baseline_hours"] == 80
    assert arjun["approved_hours"] == 10.0
    assert {t["task_id"]: t["approved_hours"] for t in arjun["tasks"]}[approved.id] == 10.0
    # KNOWN (roadmap 5.3): "In-Progress" (current flow) is not recognised as
    # in progress, so the engineer's status falls through to "—".
    assert engineers["Ravi Kumar"]["progress_status"] == "—"


def test_work_summary_is_bu_head_only(client, world, summary_project):
    project_id, _ = summary_project

    assert client.get(f"/api/projects/{project_id}/work-summary", headers=world.lead_h).status_code == 403
    assert client.get("/api/projects/999999/work-summary", headers=world.bu_h).status_code == 404
