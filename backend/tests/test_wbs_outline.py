"""WBS upload from the outline workbook: column A phase, column B bold task / normal subtask
(app/services/wbs_outline.py). The template itself must upload cleanly."""

import io

import models
from app.services.wbs_outline import PHASES, TEMPLATE_ROWS, looks_like_outline, parse_outline, write_template


def _upload(client, world, project_id, content, name="wbs.xlsx", phase=None):
    data = {"phase": phase} if phase else {}
    return client.post(
        f"/api/projects/{project_id}/wbs-upload",
        files={"file": (name, io.BytesIO(content), "application/octet-stream")},
        data=data,
        headers=world.lead_h,
    )


def _tree(db, project_id):
    nodes = db.query(models.WbsNode).filter_by(project_id=project_id).order_by(models.WbsNode.id).all()
    by_id = {n.id: n for n in nodes}
    return [(n.phase, n.wbs_code, n.task_name, by_id[n.parent_id].task_name if n.parent_id else None) for n in nodes]


def test_the_template_reads_back_as_written():
    rows = parse_outline(write_template())

    assert [(r.phase, r.name, r.is_task) for r in rows] == [
        (phase, name, is_task) for phase in PHASES for name, is_task in TEMPLATE_ROWS[phase]
    ]
    assert looks_like_outline(write_template())


def test_uploading_the_template_creates_the_tasks_and_subtasks_per_phase(client, db, world):
    project_id = world.create_project()["id"]

    response = _upload(client, world, project_id, write_template())

    assert response.status_code == 200, response.text
    assert response.json() == {"created": 15, "updated": 0, "phase": None}
    tree = _tree(db, project_id)
    assert tree[:3] == [
        ("Space Planning", "1.", "Carry out electrical load estimate & compare with the concept report", None),
        (
            "Space Planning",
            "1.1",
            "Indicate the location of substations / LV rooms",
            "Carry out electrical load estimate & compare with the concept report",
        ),
        (
            "Space Planning",
            "1.2",
            "Indicate the major services routing",
            "Carry out electrical load estimate & compare with the concept report",
        ),
    ]
    assert {phase for phase, *_ in tree} == set(PHASES)
    assert [code for _, code, _, parent in tree if parent is None] == ["1.", "2.", "3.", "4.", "5."]
    lead = db.query(models.WbsNode).filter_by(project_id=project_id).first()
    assert (lead.assigned_lead, lead.assigned_lead_user_id, lead.deliverable_status) == (
        "Anita Kumar",
        world.lead_e.id,
        "To Do",
    )


def test_uploading_the_same_workbook_again_adds_nothing(client, db, world):
    project_id = world.create_project()["id"]
    _upload(client, world, project_id, write_template())

    again = _upload(client, world, project_id, write_template())

    assert again.json() == {"created": 0, "updated": 15, "phase": None}
    assert db.query(models.WbsNode).filter_by(project_id=project_id).count() == 15


def test_phase_names_are_matched_loosely_and_blank_phase_cells_continue_the_block(client, db, world):
    project_id = world.create_project()["id"]
    workbook = write_template({"BOH area rcp coordination": [("Ceilings", True), ("Corridor RCP", False)]})

    assert _upload(client, world, project_id, workbook).status_code == 200
    assert _tree(db, project_id) == [
        ("BoH Area RCP Coordination", "1.", "Ceilings", None),
        ("BoH Area RCP Coordination", "1.1", "Corridor RCP", "Ceilings"),
    ]


def test_bad_outlines_are_refused_with_the_row_number(client, world):
    project_id = world.create_project()["id"]

    unknown = _upload(client, world, project_id, write_template({"Design": [("Task", True)]}))
    assert unknown.status_code == 400 and "Row 1: 'Design' is not one of the five phases" in unknown.json()["detail"]

    orphan = _upload(client, world, project_id, write_template({"Submission": [("Compile", False)]}))
    assert orphan.status_code == 400 and "Row 1: 'Compile' is a subtask (not bold)" in orphan.json()["detail"]


def test_a_phase_chosen_on_the_page_overrides_column_a(client, db, world):
    project_id = world.create_project()["id"]

    response = _upload(client, world, project_id, write_template(), phase="Submission")

    assert response.status_code == 200, response.text
    assert {phase for phase, *_ in _tree(db, project_id)} == {"Submission"}


def test_the_header_based_csv_still_works(client, db, world):
    project_id = world.create_project()["id"]
    csv = (
        b"WBS Code,Task Name,Parent WBS Code,Phase\n"
        b"10.,Load estimate,,STR Coordination\n"
        b"10.1,Substations,10.,STR Coordination\n"
    )

    response = _upload(client, world, project_id, csv, name="wbs.csv")

    assert response.status_code == 200, response.text
    assert _tree(db, project_id) == [
        ("STR Coordination", "10.", "Load estimate", None),
        ("STR Coordination", "10.1", "Substations", "Load estimate"),
    ]
