"""Duplicating a task (with its subtasks) or a subtask (app/services/wbs_duplicate.py).

The copy gets the next free WBS code at its level and starts To Do, with no hours.
"""

import models
from app.domain.wbs import next_code

DUPLICATE = "/api/wbs-nodes/{}/duplicate"


def _tree(make, world, project_id, code="1", subtask_codes=("1.1", "1.2")):
    task = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, wbs_code=code, task_name="Cable routing")
    subtasks = [
        make.wbs_node(
            project_id,
            world.lead_e,
            engineer=world.emp1,
            parent_id=task.id,
            wbs_code=sub_code,
            task_name=f"Level {n}",
            estimated_hours=4,
            deliverable_status="Done",
        )
        for n, sub_code in enumerate(subtask_codes, start=1)
    ]
    return task, subtasks


def _children(db, task_id):
    return db.query(models.WbsNode).filter_by(parent_id=task_id).order_by(models.WbsNode.id).all()


def test_next_code_follows_the_highest_number_at_its_level():
    assert next_code("", ["1", "2.", "1.1", "7", "SP-01", None]) == "8"  # tasks; subtask codes ignored
    assert next_code("1.", ["1", "1.1", "1.4", "1.10", "11.2", "2.9"]) == "1.11"
    assert next_code("3.", ["1", "1.1"]) == "3.1"  # the first subtask


def test_a_subtask_copy_goes_under_the_same_task_with_the_next_free_code(client, db, make, world, governed):
    project_id, *_ = governed
    task, (first, _) = _tree(make, world, project_id, subtask_codes=("1.1", "1.4"))  # 1.2, 1.3 deleted earlier

    response = client.post(DUPLICATE.format(first.id), headers=world.lead_h)

    assert response.status_code == 201, response.text
    copy = response.json()
    assert (copy["wbs_code"], copy["task_name"], copy["parent_id"]) == ("1.5", "Level 1", task.id)
    assert (copy["deliverable_status"], copy["estimated_hours"]) == ("To Do", 4)  # starts fresh, same plan
    assert copy["assigned_engineer_id"] == world.emp1.id


def test_a_task_copy_brings_copies_of_its_subtasks(client, db, make, world):
    project_id = world.create_project()["id"]  # an empty WBS: codes 1 and 3 only
    task, _ = _tree(make, world, project_id, code="1")
    make.wbs_node(project_id, world.lead_e, wbs_code="3", task_name="Another task")

    response = client.post(DUPLICATE.format(task.id), headers=world.lead_h)

    assert response.status_code == 201, response.text
    copy = response.json()
    assert (copy["wbs_code"], copy["task_name"], copy["parent_id"]) == ("4", "Cable routing", None)
    subtasks = _children(db, copy["id"])
    assert [(s.wbs_code, s.task_name, s.deliverable_status) for s in subtasks] == [
        ("4.1", "Level 1", "To Do"),
        ("4.2", "Level 2", "To Do"),
    ]
    assert [s.wbs_code for s in _children(db, task.id)] == ["1.1", "1.2"]  # the original is untouched


def test_an_engineer_duplicates_own_subtasks_but_never_a_task(client, db, make, world, governed):
    project_id, *_ = governed
    task, (mine, _) = _tree(make, world, project_id)
    theirs = make.wbs_node(project_id, world.lead_e, engineer=world.emp2, parent_id=task.id, wbs_code="1.3")

    refused_task = client.post(DUPLICATE.format(task.id), headers=world.eng_h)
    refused_other = client.post(DUPLICATE.format(theirs.id), headers=world.eng_h)
    allowed = client.post(DUPLICATE.format(mine.id), headers=world.eng_h)

    assert refused_task.status_code == 403 and "Only the project's lead" in refused_task.json()["detail"]
    assert refused_other.status_code == 403
    assert allowed.status_code == 201, allowed.text
    copy = db.get(models.WbsNode, allowed.json()["id"])
    assert (copy.wbs_code, copy.created_by_user_id) == ("1.4", world.engineer.id)  # theirs to delete again


def test_new_subtasks_never_reuse_a_deleted_subtasks_code(client, db, make, world, governed):
    project_id, *_ = governed
    task, _ = _tree(make, world, project_id, subtask_codes=("1.1", "1.3"))  # 1.2 was deleted
    subtask = {"task_name": "Risers", "estimated_hours": 4, "start_date": "2026-09-01", "end_date": "2026-09-01"}

    response = client.post(f"/api/wbs-nodes/{task.id}/subtasks", json=subtask, headers=world.lead_h)

    assert response.status_code == 201, response.text  # "count + 1" would have made a second 1.3
    assert response.json()["wbs_code"] == "1.4"
