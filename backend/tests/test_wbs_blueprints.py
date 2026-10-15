"""Phase blueprints: "+" on a phase card adds that phase's standard tasks (app/services/wbs_blueprints.py).

The app's blueprints are the CD/SD/DD WBS nodes (test_wbs_nodes.py); the five original phases'
workbooks, kept in tests/fixtures/blueprints/, exercise the mechanism here on small, stable data.
"""

from pathlib import Path

import pytest

import models
from app.domain.wbs_nodes import NodeSheet
from app.services import wbs_blueprints
from app.services.wbs_blueprints import blueprint_rows

ADD = "/api/projects/{}/wbs-blueprints/{}"
FIXTURES = Path(__file__).parent / "fixtures" / "blueprints"
OLD_FIVE = {
    key: NodeSheet(key, phase, "OLD", workbook, "xl/worksheets/sheet1.xml")
    for key, phase, workbook in (
        ("space-planning", "Space Planning", "space_planning.xlsx"),
        ("str-coordination", "STR Coordination", "str_coordination.xlsx"),
        ("id-rcp-coordination", "ID - RCP Coordination", "id_coordination.xlsx"),
        ("boh-area-rcp-coordination", "BoH Area RCP Coordination", "boh_area_rcp_coordination.xlsx"),
        ("submission", "Submission", "submission.xlsx"),
    )
}


@pytest.fixture(autouse=True)
def old_blueprints(monkeypatch):
    """The five old phases' workbooks, served as the app's blueprints for these tests only."""
    monkeypatch.setattr(wbs_blueprints, "BLUEPRINT_DIR", FIXTURES)
    monkeypatch.setattr(wbs_blueprints, "BLUEPRINTS", OLD_FIVE)
    blueprint_rows.cache_clear()
    yield
    blueprint_rows.cache_clear()


def _nodes(db, project_id):
    db.expire_all()
    return db.query(models.WbsNode).filter_by(project_id=project_id).all()


def test_each_blueprint_is_listed_and_reads_cleanly(client, world):
    listed = client.get("/api/wbs-blueprints", headers=world.lead_h).json()

    assert [b["phase"] for b in listed] == [node.phase for node in OLD_FIVE.values()]
    for blueprint in listed:
        rows = blueprint_rows(blueprint["key"])
        assert rows[0].is_task, blueprint  # each starts with a task
        assert blueprint["tasks"] > 0 and blueprint["tasks"] + blueprint["subtasks"] == len(rows)
        assert {row.phase for row in rows} == {blueprint["phase"]}


def test_a_lead_adds_one_phase_and_only_that_phase(client, db, world):
    project_id = world.create_project()["id"]
    rows = blueprint_rows("space-planning")

    response = client.post(ADD.format(project_id, "space-planning"), headers=world.lead_h)

    assert response.status_code == 200, response.text
    assert response.json() | {"created_ids": None, "same_as": None} == {
        "phase": "Space Planning",
        "created": len(rows),
        "skipped": 0,
        "created_ids": None,
        "same_as": None,
    }
    nodes = _nodes(db, project_id)
    assert {n.phase for n in nodes} == {"Space Planning"}
    tasks = [n for n in nodes if n.parent_id is None]
    assert [t.task_name for t in tasks] == [r.name for r in rows if r.is_task]
    first = tasks[0]
    under_first = sorted((n.wbs_code for n in nodes if n.parent_id == first.id), key=lambda c: int(c.split(".")[-1]))
    assert under_first[:2] == [f"{first.wbs_code.rstrip('.')}.1", f"{first.wbs_code.rstrip('.')}.2"]


def test_adding_a_blueprint_again_skips_what_is_already_there(client, db, world):
    project_id = world.create_project()["id"]
    total = len(blueprint_rows("submission"))
    client.post(ADD.format(project_id, "submission"), headers=world.lead_h)
    removed = next(n for n in _nodes(db, project_id) if n.parent_id is not None)
    assert client.delete(f"/api/wbs-nodes/{removed.id}", headers=world.lead_h).status_code == 200

    again = client.post(ADD.format(project_id, "submission"), headers=world.lead_h).json()

    assert (again["created"], again["skipped"]) == (1, total - 1)  # only the deleted one comes back
    assert len(_nodes(db, project_id)) == total


def test_two_phases_side_by_side_get_their_own_codes(client, db, world):
    project_id = world.create_project()["id"]
    client.post(ADD.format(project_id, "space-planning"), headers=world.lead_h)
    client.post(ADD.format(project_id, "str-coordination"), headers=world.lead_h)

    codes = [n.wbs_code for n in _nodes(db, project_id)]

    assert len(codes) == len(set(codes))  # never a duplicate code


def test_only_the_projects_leads_add_blueprints(client, world):
    project_id = world.create_project()["id"]

    for headers in (world.eng_h, world.other_lead_h, world.bu_h):
        assert client.post(ADD.format(project_id, "space-planning"), headers=headers).status_code == 403
    assert client.post(ADD.format(project_id, "no-such-phase"), headers=world.lead_h).status_code == 404


def test_adding_a_blueprint_is_in_the_audit_log(client, world):
    project_id = world.create_project()["id"]

    client.post(ADD.format(project_id, "id-rcp-coordination"), headers=world.lead_h)

    latest = client.get("/api/audit/mine", headers=world.lead_h).json()["events"][0]
    assert latest["summary"] == "Added the ID - RCP Coordination blueprint"
    assert latest["project_id"] == project_id


def test_the_question_before_adding_says_how_much_is_already_there(client, world):
    project_id = world.create_project()["id"]
    rows = blueprint_rows("submission")
    tasks = sum(1 for r in rows if r.is_task)

    before = client.get(ADD.format(project_id, "submission"), headers=world.lead_h).json()
    client.post(ADD.format(project_id, "submission"), headers=world.lead_h)
    after = client.get(ADD.format(project_id, "submission"), headers=world.lead_h).json()

    assert (before["present_tasks"], before["present_subtasks"], before["missing"]) == (0, 0, len(rows))
    assert (after["present_tasks"], after["present_subtasks"], after["missing"]) == (tasks, len(rows) - tasks, 0)
    assert client.get(ADD.format(project_id, "submission"), headers=world.eng_h).status_code == 403


def test_adding_again_makes_a_full_copy_at_the_bottom_and_names_what_each_repeats(client, db, world):
    project_id = world.create_project()["id"]
    rows = blueprint_rows("submission")
    client.post(ADD.format(project_id, "submission"), headers=world.lead_h)
    first = {n.id: n.wbs_code for n in _nodes(db, project_id)}

    copy = client.post(ADD.format(project_id, "submission") + "?again=true", headers=world.lead_h).json()

    assert (copy["created"], copy["skipped"]) == (len(rows), 0)
    new = [n for n in _nodes(db, project_id) if n.id in set(copy["created_ids"])]
    assert len(new) == len(rows)
    old_tasks = [int(code.rstrip(".")) for code in first.values() if code.count(".") == 1 and code.endswith(".")]
    new_tasks = [n for n in new if n.parent_id is None]
    assert min(int(t.wbs_code.rstrip(".")) for t in new_tasks) > max(old_tasks)  # numbered after: at the bottom
    same_as = {int(k): v for k, v in copy["same_as"].items()}
    assert set(same_as) == {n.id for n in new} and set(same_as.values()) <= set(first.values())
    first_task = new_tasks[0]
    assert same_as[first_task.id] == min(first.values(), key=lambda c: int(c.split(".")[0]))  # repeats task 1


def test_the_wbs_lists_codes_in_number_order(client, make, world):
    project_id = world.create_project()["id"]
    for code in ("10.", "2.", "1.", "1.10", "1.2", "11."):
        make.wbs_node(project_id, world.lead_e, wbs_code=code)

    listed = client.get(f"/api/projects/{project_id}/wbs-structure", headers=world.lead_h).json()

    assert [n["wbs_code"] for n in listed] == ["1.", "1.2", "1.10", "2.", "10.", "11."]
