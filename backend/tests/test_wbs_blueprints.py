"""Phase blueprints: "+" on a phase card adds that phase's standard tasks (app/services/wbs_blueprints.py)."""

import models
from app.services.wbs_blueprints import BLUEPRINTS, blueprint_rows

ADD = "/api/projects/{}/wbs-blueprints/{}"


def _nodes(db, project_id):
    db.expire_all()
    return db.query(models.WbsNode).filter_by(project_id=project_id).all()


def test_all_five_blueprints_ship_with_the_app_and_read_cleanly(client, world):
    listed = client.get("/api/wbs-blueprints", headers=world.lead_h).json()

    assert [b["phase"] for b in listed] == [phase for phase, _ in BLUEPRINTS.values()]
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
    assert response.json() == {"phase": "Space Planning", "created": len(rows), "skipped": 0}
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

    assert again == {"phase": "Submission", "created": 1, "skipped": total - 1}  # only the deleted one comes back
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

    client.post(ADD.format(project_id, "id-coordination"), headers=world.lead_h)

    latest = client.get("/api/audit/mine", headers=world.lead_h).json()["events"][0]
    assert latest["summary"] == "Added the id coordination blueprint"
    assert latest["project_id"] == project_id
