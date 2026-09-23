"""create_user.py: account creation rules, including the lead discipline (roadmap 4.1)."""

import pytest

from create_user import create_user, set_lead_discipline

PASSWORD = "Longenough1"


def test_lead_is_created_with_normalized_discipline_and_appears_in_dropdown(client, db, world):
    lead = create_user(db, "lead.new", PASSWORD, "New Lead", "lead", None, "mechanical")

    assert lead.discipline == "Mechanical"
    names = {row["name"] for row in client.get("/api/project-leads?discipline=mechanical", headers=world.bu_h).json()}
    assert "New Lead" in names


@pytest.mark.parametrize(
    ("role", "discipline", "message"),
    [
        ("lead", None, "Lead accounts need a discipline"),
        ("lead", "Plumbing", "Invalid discipline"),
        ("bu_head", "Electrical", "Only lead accounts have a discipline"),
    ],
)
def test_discipline_rules(db, role, discipline, message):
    with pytest.raises(SystemExit, match=message):
        create_user(db, "someone", PASSWORD, "Someone", role, None, discipline)


def test_engineer_must_link_to_an_existing_employee(db, make):
    with pytest.raises(SystemExit, match="must be linked"):
        create_user(db, "eng.x", PASSWORD, "Eng", "engineer", None)
    with pytest.raises(SystemExit, match="No employee"):
        create_user(db, "eng.x", PASSWORD, "Eng", "engineer", 999999)

    employee = make.employee("Real Person")
    assert create_user(db, "eng.x", PASSWORD, "Eng", "engineer", employee.id).employee_id == employee.id


def test_short_password_and_duplicate_username_are_rejected(db, make):
    make.user("taken", "bu_head", "Taken")
    with pytest.raises(SystemExit, match="at least 8"):
        create_user(db, "new", "short", "X", "bu_head", None)
    with pytest.raises(SystemExit, match="already exists"):
        create_user(db, "taken", PASSWORD, "X", "bu_head", None)


def test_set_lead_discipline_updates_existing_lead_only(db, make):
    make.user("old.lead", "lead", "Old Lead")
    make.user("boss", "bu_head", "Boss")

    assert set_lead_discipline(db, "old.lead", "bim").discipline == "BIM"
    with pytest.raises(SystemExit, match="only lead accounts"):
        set_lead_discipline(db, "boss", "BIM")
    with pytest.raises(SystemExit, match="does not exist"):
        set_lead_discipline(db, "ghost", "BIM")
