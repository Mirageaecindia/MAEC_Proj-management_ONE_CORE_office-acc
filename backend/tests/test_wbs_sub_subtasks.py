"""Sub-subtasks: "+" on a subtask splits it into reference steps (decided 2026-10-07).

They move To Do -> In-Progress -> Done, take no Login/Logout, no hours and no
estimate, and never hold up their subtask. Delete and duplicate take them along.
"""

import models
from app.domain.wbs import NO_DEEPER
from app.services.tracking import NOT_FOR_TIME

ADD = "/api/wbs-nodes/{}/subtasks"
START = "/api/subtask-tracking/start"
ADVANCE = "/api/wbs-nodes/{}/advance-status"


def _tree(make, world, project_id):
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code="30", task_name="Risers")
    subtask = make.wbs_node(
        project_id, world.lead_e, engineer=world.emp1, parent_id=task.id, wbs_code="30.1", estimated_hours=4
    )
    return task, subtask


def _add(client, headers, parent_id, name="Check the sleeves", **extra):
    return client.post(ADD.format(parent_id), json={"task_name": name, **extra}, headers=headers)


def test_plus_on_a_subtask_adds_a_reference_step_under_it(client, make, world, governed):
    project_id, *_ = governed
    _, subtask = _tree(make, world, project_id)

    response = _add(client, world.lead_h, subtask.id, estimated_hours=6)

    assert response.status_code == 201, response.text
    step = response.json()
    assert (step["wbs_code"], step["parent_id"], step["deliverable_status"]) == ("30.1.1", subtask.id, "To Do")
    assert step["estimated_hours"] is None  # no estimate: nothing to plan or count
    detail = client.get(f"/api/wbs-nodes/{step['id']}", headers=world.eng_h).json()
    assert (detail["node_type"], detail["reference_only"]) == ("subtask", True)
    assert client.get(f"/api/wbs-nodes/{subtask.id}", headers=world.eng_h).json()["reference_only"] is False


def test_three_levels_at_most(client, make, world, governed):
    project_id, *_ = governed
    _, subtask = _tree(make, world, project_id)
    step = _add(client, world.lead_h, subtask.id).json()

    deeper = _add(client, world.lead_h, step["id"])

    assert deeper.status_code == 400 and deeper.json()["detail"] == NO_DEEPER


def test_a_step_takes_no_login_moves_like_a_subtask_and_never_holds_up_its_subtask(client, make, world, governed):
    project_id, *_ = governed
    _, subtask = _tree(make, world, project_id)
    step = _add(client, world.lead_h, subtask.id).json()

    login = client.post(START, json={"subtask_id": step["id"]}, headers=world.eng_h)
    assert login.status_code == 400 and login.json()["detail"] == NOT_FOR_TIME

    for status in ("In-Progress", "Done"):
        moved = client.post(ADVANCE.format(subtask.id), json={"new_status": status}, headers=world.eng_h)
        assert moved.status_code == 200, moved.text  # the open step doesn't block the subtask
    for status in ("In-Progress", "Done"):
        moved = client.post(ADVANCE.format(step["id"]), json={"new_status": status}, headers=world.eng_h)
        assert moved.status_code == 200, moved.text


def test_deleting_a_task_or_a_subtask_takes_its_steps_along(client, db, make, world, governed):
    project_id, *_ = governed
    task, subtask = _tree(make, world, project_id)
    other = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=task.id, wbs_code="30.2")
    first = _add(client, world.lead_h, subtask.id).json()["id"]
    second = _add(client, world.lead_h, other.id).json()["id"]

    assert client.delete(f"/api/wbs-nodes/{subtask.id}", headers=world.lead_h).status_code == 200
    assert db.get(models.WbsNode, first) is None and db.get(models.WbsNode, second) is not None

    deleted = client.delete(f"/api/wbs-nodes/{task.id}", headers=world.lead_h).json()
    assert deleted["subtasks"] == 2  # the subtask and its step
    db.expire_all()
    assert db.get(models.WbsNode, second) is None


def test_duplicating_copies_the_steps_too(client, db, make, world):
    project_id = world.create_project()["id"]
    task, subtask = _tree(make, world, project_id)
    _add(client, world.lead_h, subtask.id, name="Step A")
    _add(client, world.lead_h, subtask.id, name="Step B")

    task_copy = client.post(f"/api/wbs-nodes/{task.id}/duplicate", headers=world.lead_h).json()
    sub_copy = client.post(f"/api/wbs-nodes/{subtask.id}/duplicate", headers=world.lead_h).json()

    codes = {n.wbs_code: n.task_name for n in db.query(models.WbsNode).filter_by(project_id=project_id)}
    assert task_copy["wbs_code"] == "31" and {"31.1.1": "Step A", "31.1.2": "Step B"}.items() <= codes.items()
    assert sub_copy["wbs_code"] == "30.2" and {"30.2.1": "Step A", "30.2.2": "Step B"}.items() <= codes.items()


def test_an_engineer_adds_steps_to_their_own_subtasks_only(client, make, world, governed):
    project_id, *_ = governed
    task, mine = _tree(make, world, project_id)
    colleagues = make.wbs_node(project_id, world.lead_e, engineer=world.emp2, parent_id=task.id, wbs_code="30.2")

    assert _add(client, world.eng_h, mine.id).status_code == 201
    assert _add(client, world.eng_h, colleagues.id).status_code == 403
