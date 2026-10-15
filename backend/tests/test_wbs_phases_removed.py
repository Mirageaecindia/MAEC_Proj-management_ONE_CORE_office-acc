"""The five original phases were removed (2026-10-15): the app offers none of them to add, and the
work already filed under them stays on its projects and keeps working.

Until the CD/SD/DD nodes (backend/data/WBS_Node_level_BREAKDOWN/) are added, the app ships no
blueprint, so the WBS page shows no phase card and a new project's WBS is empty.
"""

LIST = "/api/projects/{}/wbs-structure?include_ancestors=true"


def test_no_phase_is_offered_to_add(client, world):
    project_id = world.create_project()["id"]

    assert client.get("/api/wbs-blueprints", headers=world.lead_h).json() == []
    assert (
        client.post(f"/api/projects/{project_id}/wbs-blueprints/space-planning", headers=world.lead_h).status_code
        == 404
    )
    assert client.get(LIST.format(project_id), headers=world.lead_h).json() == []  # a new project starts empty


def test_work_under_an_old_phase_stays_and_keeps_working(client, make, world, governed):
    project_id, *_ = governed
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="50", phase="Space Planning")

    added = client.post(
        f"/api/wbs-nodes/{task.id}/subtasks",
        json={
            "task_name": "Check the riser drawing",
            "estimated_hours": 4,
            "start_date": "2026-09-15",
            "end_date": "2026-09-15",
        },
        headers=world.lead_h,
    )
    assert added.status_code == 201, added.text
    assert added.json()["phase"] == "Space Planning"  # under its task's phase

    moved = client.post(
        f"/api/wbs-nodes/{added.json()['id']}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h
    )
    assert moved.status_code == 200, moved.text

    for headers in (world.lead_h, world.eng_h, world.bu_h):
        rows = {n["wbs_code"]: n for n in client.get(LIST.format(project_id), headers=headers).json()}
        assert rows["50"]["phase"] == "Space Planning"
        assert client.get(f"/api/wbs-nodes/{task.id}", headers=headers).status_code == 200
