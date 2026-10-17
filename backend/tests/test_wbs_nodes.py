"""The WBS nodes (2026-10-15): the sheets of the CD/SD/DD workbooks in app/blueprints/, loaded as
they are. The sheet name is the node, a bold row a task, a normal row a subtask under it; rows
marked "NOT INCLUDED" and notes outside the item column are left out. The five original phases
are no longer offered, and the work already filed under them keeps working.
"""

import models
from app.domain.wbs_nodes import OTHERS_NODE, node_phases
from app.services.wbs_blueprints import BLUEPRINTS, blueprint_rows

LIST = "/api/projects/{}/wbs-structure?include_ancestors=true"
ADD = "/api/projects/{}/wbs-blueprints/{}"


def names(key):
    return [row.name for row in blueprint_rows(key)]


def tasks(key):
    return [row.name for row in blueprint_rows(key) if row.is_task]


def test_each_sheet_is_a_node_stage_by_stage(client, world):
    listed = client.get("/api/wbs-blueprints", headers=world.lead_h).json()

    assert [b["stage"] for b in listed] == ["CD"] * 2 + ["SD"] * 6 + ["DD"] * 12
    assert [b["phase"] for b in listed][:3] == ["CD - Space Planning", "CD-Submission", "SD-Comment Session"]
    assert "SD- STR Coodination" in node_phases()  # the sheet name, as it is
    assert not {"Space Planning", "Submission"} & {b["phase"] for b in listed}  # the original five are gone
    longest = models.WbsNode.task_name.type.length
    for blueprint in listed:
        rows = blueprint_rows(blueprint["key"])
        assert rows[0].is_task, blueprint  # each starts with a task
        assert blueprint["tasks"] + blueprint["subtasks"] == len(rows)
        assert all(len(row.name) <= longest for row in rows)  # the 249-character step fits


def test_bold_rows_are_tasks_and_normal_rows_their_subtasks():
    assert tasks("cd-submission") == ["100% CD Report", "100% CD Calculations", "100% CD Schematics", "100% CD Layouts"]
    sheet = names("cd-submission")
    assert sheet[1].startswith("Identify any risks")  # the first subtask of 100% CD Report


def test_not_included_rows_and_notes_are_left_out():
    assert "STR Openings" not in names("sd-str-coodination")  # marked NOT INCLUDED
    assert "RCP Coordination" not in names("sd-id-coodination")
    assert "Response of 100% SD comments tracker" not in names("dd-comment-session")
    assert "Response of 100% SD comments tracker" in names("sd-comment-session")  # not marked there
    assert tasks("dd-major-services-routing") == ["HVAC", "Elect", "PHE"]
    every = {name for key in BLUEPRINTS for name in names(key)}
    assert not {"NOT INCLUDED", "NO TASKS", "Custom Requirement", "-"} & every
    assert not [name for name in every if name.startswith("Shajjad")]


def test_subtasks_before_any_task_go_under_a_task_named_after_the_node():
    assert tasks("dd-deliverable-setup") == ["DD-Deliverable Setup"]
    assert names("dd-deliverable-setup")[1] == "Engrs to provide the List of Deliverables to BIM Manager"
    assert names("dd-space-planning") == [
        "DD-Space Planning",
        "Validate all the MEP space planning as per the comments received on 100% SD package",
        "Issue comments/revised space planning to arch/ID",
        "Obtain revised arch/ID layouts based on the above comments",
    ]


def test_a_lead_adds_a_node_and_its_tasks_carry_the_node(client, db, world):
    project_id = world.create_project()["id"]

    added = client.post(ADD.format(project_id, "dd-major-services-routing"), headers=world.lead_h)

    assert added.status_code == 200, added.text
    rows = blueprint_rows("dd-major-services-routing")
    assert added.json()["created"] == len(rows)
    db.expire_all()
    nodes = db.query(models.WbsNode).filter_by(project_id=project_id).all()
    assert {n.phase for n in nodes} == {"DD-Major Services Routing"}
    assert max(len(n.task_name) for n in nodes) == 249


def test_a_task_is_added_by_hand_to_a_node_not_to_an_unknown_phase(client, world):
    project_id = world.create_project()["id"]
    create = lambda phase: client.post(  # noqa: E731
        f"/api/projects/{project_id}/wbs-nodes", json={"task_name": "Extra check", "phase": phase}, headers=world.lead_h
    )

    assert create("DD - Submission").status_code == 201
    assert create("Made-up phase").status_code == 422


def test_work_under_an_original_phase_stays_and_keeps_working(client, make, world, governed):
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


def test_others_takes_the_leads_own_tasks_and_subtasks(client, db, world):
    project_id = world.create_project()["id"]
    assert node_phases()[-1] == OTHERS_NODE == "Others"  # after the DD nodes
    assert "Others" not in {b["phase"] for b in client.get("/api/wbs-blueprints", headers=world.lead_h).json()}
    assert client.post(ADD.format(project_id, "others"), headers=world.lead_h).status_code == 404  # no standard tasks

    one_day = {"estimated_hours": 4, "start_date": "2026-09-15", "end_date": "2026-09-15"}  # a subtask's plan
    tasks = []
    for name in ("Client workshop", "Site visit report"):  # any number of tasks, named by the lead
        created = client.post(
            f"/api/projects/{project_id}/wbs-nodes", json={"task_name": name, "phase": "Others"}, headers=world.lead_h
        )
        assert created.status_code == 201, created.text
        tasks.append(created.json())
    for name in ("Prepare the agenda", "Send the minutes"):
        sub = client.post(
            f"/api/wbs-nodes/{tasks[0]['id']}/subtasks", json={"task_name": name, **one_day}, headers=world.lead_h
        )
        assert sub.status_code == 201, sub.text
        assert sub.json()["phase"] == "Others"

    listed = client.get(f"/api/projects/{project_id}/wbs-structure", headers=world.lead_h).json()
    assert sorted(n["task_name"] for n in listed if n["phase"] == "Others") == [
        "Client workshop",
        "Prepare the agenda",
        "Send the minutes",
        "Site visit report",
    ]
