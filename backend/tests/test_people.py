"""People: profiles in this app (app/services/provisioning.py).

The BU Head uploads an HR export, or adds one person; everyone without a profile gets an
employee record and an engineer profile named by their work email. No passwords: people sign
in at MAEC One, and their profile is linked to their MAEC One account by that email at their
first visit (app/core/identity.py). Resetting passwords, deactivating and deleting moved to
MAEC One.
"""

import io
from datetime import UTC, datetime

import pytest

import models
from app.core.errors import ConflictError
from app.core.security import NO_PASSWORD
from app.services.provisioning import Provisioning

IMPORT, PEOPLE, ME = "/api/people/import", "/api/people", "/api/auth/me"

# Shaped like the real export: extra columns (phones), Windows encoding, non-breaking spaces.
HR_EXPORT = (
    "Employee Id,First Name,Last Name,Full Name,Work Email,Job Role,Work Phone Number,Personal Phone Number\r\n"
    "M0101,Kavya,Raman,Kavya Raman,Kavya.Raman@MirageAEC.com,Senior\xa0Electrical\xa0Engineer,044 1111,98400 11111\r\n"
    "M0102,Suresh,Babu,Suresh  Babu ,suresh.babu@mirageaec.com,BIM Modeller - PHE,044 2222,98400 22222\r\n"
).encode("cp1252")


def _upload(client, headers, content=HR_EXPORT, name="people.csv"):
    return client.post(IMPORT, files={"file": (name, io.BytesIO(content), "text/csv")}, headers=headers)


def test_the_bu_head_imports_engineers_without_passwords(client, db, world):
    response = _upload(client, world.bu_h)

    assert response.status_code == 200, response.text
    created = response.json()["created"]
    assert created == [
        {"username": "kavya.raman@mirageaec.com", "full_name": "Kavya Raman", "employee_code": "M0101"},
        {"username": "suresh.babu@mirageaec.com", "full_name": "Suresh Babu", "employee_code": "M0102"},  # cleaned
    ]  # no temporary password, nor anything else to hand over
    assert response.json()["skipped"] == []

    kavya = db.query(models.User).filter_by(username="kavya.raman@mirageaec.com").one()
    employee = db.get(models.Employee, kavya.employee_id)
    assert (kavya.role, kavya.full_name, kavya.must_change_password) == ("engineer", "Kavya Raman", False)
    assert kavya.password_hash == NO_PASSWORD and kavya.core_user_id is None
    assert (employee.employee_code, employee.name, employee.role_title) == (
        "M0101",
        "Kavya Raman",
        "Senior Electrical Engineer",
    )
    assert not hasattr(employee, "phone") and "98400" not in str(vars(employee))  # phones are never read


def test_an_imported_person_signs_in_at_maec_one_and_is_linked_by_email(client, db, core, world):
    _upload(client, world.bu_h)
    kavya = core.headers(core.sign_in("Kavya.Raman@MirageAEC.com", "Kavya R", core_id="core-kavya"))  # any case

    me = client.get(ME, headers=kavya)

    assert me.status_code == 200, me.text
    assert (me.json()["username"], me.json()["full_name"], me.json()["role"]) == (
        "kavya.raman@mirageaec.com",
        "Kavya Raman",  # this app's name, not Core's
        "engineer",
    )
    assert db.query(models.User).filter_by(username="kavya.raman@mirageaec.com").one().core_user_id == "core-kavya"


def test_people_already_known_or_repeated_are_skipped_with_the_reason(client, db, make, world):
    make.employee("Lakshmi Iyer").employee_code = "M0201"  # an employee record without an account
    db.commit()
    taken = make.employee("Arun Kumar")
    taken.employee_code = "M0202"
    make.user("arun@mirageaec.com", "engineer", "Arun Kumar", employee_id=taken.id)
    db.commit()
    content = (
        b"Employee Id,Full Name,Work Email,Job Role\n"
        b"M0201,Lakshmi Iyer,lakshmi@mirageaec.com,PHE Engineer\n"  # gets an account, same employee record
        b"M0202,Arun Kumar,arun.k@mirageaec.com,Intern\n"  # his employee record has an account
        b"M0203,Divya,ARUN@mirageaec.com,Intern\n"  # that email is a username already
        b"M0204,Divya S,lakshmi@mirageaec.com,Intern\n"  # earlier in the file
        b"M0205,No Email,,Intern\n"
        b"M0206,Bad Email,not-an-email,Intern\n"
        b",,,\n"  # a blank line
    )

    response = _upload(client, world.bu_h, content)

    assert response.status_code == 200, response.text
    assert [c["username"] for c in response.json()["created"]] == ["lakshmi@mirageaec.com"]
    assert [(s["row"], s["reason"]) for s in response.json()["skipped"]] == [
        (3, "Already a profile for employee M0202."),
        (4, "Already has a profile."),
        (5, "Appears earlier in the file."),
        (6, "Employee Id, Full Name and Work Email are all needed."),
        (7, "The work email is not a valid address."),
    ]
    assert db.query(models.Employee).filter_by(employee_code="M0201").count() == 1  # linked, not duplicated
    assert _upload(client, world.bu_h, content).json()["created"] == []  # importing again changes nothing


def test_a_file_without_the_needed_columns_is_refused_and_names_them(client, world):
    response = _upload(client, world.bu_h, b"Name,Email\nKavya,kavya@mirageaec.com\n")

    assert response.status_code == 400
    assert '"Employee Id", "Full Name", "Work Email", "Job Role"' in response.json()["detail"]


def test_only_the_bu_head_imports_or_adds_people(client, world):
    one = {"employee_code": "M0301", "full_name": "Neha Rao", "email": "neha@mirageaec.com", "job_role": "Intern"}
    assert _upload(client, world.eng_h).status_code == 403
    assert _upload(client, world.lead_h).status_code == 403  # a project lead is still an engineer
    assert client.post(PEOPLE, json=one, headers=world.lead_h).status_code == 403


def test_the_bu_head_adds_one_person_who_has_a_seat_but_no_profile(client, db, core, world):
    """Someone given a seat in MAEC One after go-live: told to ask a Business Head, who adds them."""
    neha = core.headers(core.sign_in("Neha.Rao@mirageaec.com", "Neha Rao", core_id="core-neha"))
    refused = client.get(ME, headers=neha)
    assert refused.status_code == 403 and refused.headers["X-Error-Code"] == "PROFILE_NOT_SET_UP"
    assert refused.json()["detail"] == "Your Project Management profile hasn't been set up yet. Ask a Business Head."
    one = {"employee_code": "M0301", "full_name": " Neha  Rao", "email": "Neha.Rao@mirageaec.com", "job_role": "Intern"}

    added = client.post(PEOPLE, json=one, headers=world.bu_h)

    assert added.status_code == 201, added.text
    assert added.json() == {"username": "neha.rao@mirageaec.com", "full_name": "Neha Rao", "employee_code": "M0301"}
    me = client.get(ME, headers=neha)
    assert me.status_code == 200 and me.json()["role"] == "engineer"
    user = db.query(models.User).filter_by(username="neha.rao@mirageaec.com").one()
    assert (user.core_user_id, user.password_hash) == ("core-neha", NO_PASSWORD)
    assert db.get(models.Employee, user.employee_id).employee_code == "M0301"
    assert client.post(PEOPLE, json=one, headers=world.bu_h).status_code == 409  # already has one
    bad = {**one, "employee_code": "M0302", "email": "not-an-email"}
    assert client.post(PEOPLE, json=bad, headers=world.bu_h).status_code == 400


def test_passwords_deactivation_and_deleting_are_managed_in_maec_one(client, world):
    arjun = world.engineer.id
    assert client.post(f"{PEOPLE}/reset-password", json={"username": "x"}, headers=world.bu_h).status_code in (404, 405)
    assert client.post(f"{PEOPLE}/{arjun}/deactivate", headers=world.bu_h).status_code == 404
    assert client.post(f"{PEOPLE}/{arjun}/reactivate", headers=world.bu_h).status_code == 404
    assert client.delete(f"{PEOPLE}/{arjun}", headers=world.bu_h).status_code == 405
    for gone in ("/api/auth/login", "/api/auth/logout", "/api/auth/change-password"):
        assert client.post(gone, json={}, headers=world.bu_h).status_code in (404, 405), gone


def _person(client, world, username):
    return next(p for p in client.get(PEOPLE, headers=world.bu_h).json() if p["username"] == username)


def test_the_bu_head_sees_everyone_with_a_profile(client, world):
    _upload(client, world.bu_h)

    people = client.get(PEOPLE, headers=world.bu_h)

    assert people.status_code == 200, people.text
    kavya = next(p for p in people.json() if p["username"] == "kavya.raman@mirageaec.com")
    assert {k: kavya[k] for k in ("full_name", "employee_code", "job_role", "is_active", "can_edit")} == {
        "full_name": "Kavya Raman",
        "employee_code": "M0101",
        "job_role": "Senior Electrical Engineer",
        "is_active": True,
        "can_edit": True,
    }
    assert not any({"password_hash", "must_change_password", "can_delete"} & set(p) for p in people.json())
    bu_head = next(p for p in people.json() if p["role"] == "bu_head")
    assert bu_head["can_edit"] is False
    assert client.get(PEOPLE, headers=world.lead_h).status_code == 403


def test_correcting_a_name_or_job_role_but_never_the_email(client, db, world, governed):
    project_id, node_a, *_ = governed
    lead = _person(client, world, world.lead_e.username)  # leads the project, so her name is copied there

    renamed = client.patch(
        f"{PEOPLE}/{lead['id']}",
        json={"full_name": " Anita  K. ", "username": "Anita.K@MirageAEC.com", "job_role": "Electrical Lead"},
        headers=world.bu_h,
    )

    assert renamed.status_code == 200, renamed.text
    assert (renamed.json()["full_name"], renamed.json()["username"], renamed.json()["job_role"]) == (
        "Anita K.",
        world.lead_e.username,  # the email is who she is in MAEC One: not edited here
        "Electrical Lead",
    )
    db.expire_all()
    assert db.get(models.Project, project_id).project_lead_electrical == "Anita K."  # the copies follow
    assert db.get(models.WbsNode, node_a.id).assigned_lead == "Anita K."
    assert db.get(models.Employee, world.lead_e.employee_id).name == "Anita K."
    assert client.get(ME, headers=world.lead_h).json()["full_name"] == "Anita K."  # still her, still signed in

    assert client.patch(f"{PEOPLE}/{lead['id']}", json={"full_name": "  "}, headers=world.bu_h).status_code == 400
    bu_head = _person(client, world, world.bu.username)
    assert client.patch(f"{PEOPLE}/{bu_head['id']}", json={"full_name": "X"}, headers=world.bu_h).status_code == 403


def _make_bu_head(client, world, person_id, confirm=True, headers=None):
    return client.post(f"{PEOPLE}/{person_id}/make-bu-head", json={"confirm": confirm}, headers=headers or world.bu_h)


def test_an_engineer_on_no_live_project_is_made_a_bu_head(client, db, core, world):
    created = _upload(client, world.bu_h).json()["created"][0]
    kavya = _person(client, world, created["username"])
    session = core.headers(core.sign_in(created["username"], "Kavya Raman"))
    assert client.get(ME, headers=session).json()["role"] == "engineer"

    assert _make_bu_head(client, world, kavya["id"], confirm=False).status_code == 400  # say yes in the dialog first
    promoted = _make_bu_head(client, world, kavya["id"])

    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "bu_head"
    assert client.get(ME, headers=session).json()["role"] == "bu_head"  # from her next click
    note = db.query(models.Notification).filter_by(notification_type="bu_head_appointed").one()
    assert (note.recipient_role, note.message) == ("bu_head", "Test BU Head made Kavya Raman a BU Head.")
    assert _person(client, world, world.bu.username)["can_remove_bu_head"] is False  # created as BU Head


def test_someone_on_a_live_project_is_not_promoted_and_the_projects_are_named(client, db, world, governed):
    project_id, *_ = governed  # Arjun is booked with tasks; Anita leads it
    project_name = db.get(models.Project, project_id).project_name
    arjun = _person(client, world, world.engineer.username)
    anita = _person(client, world, world.lead_e.username)

    refused = _make_bu_head(client, world, arjun["id"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        f"Arjun Mehta is assigned to {project_name} as engineer. "
        "Remove them from these projects before making them a BU Head."
    )
    assert f"{project_name} as lead" in _make_bu_head(client, world, anita["id"]).json()["detail"]

    db.get(models.Project, project_id).archived_at = datetime.now(UTC)  # a finished project doesn't count
    db.commit()
    assert _make_bu_head(client, world, arjun["id"]).status_code == 200


def test_the_bu_head_role_is_taken_back_from_a_promoted_bu_head_only(client, db, world):
    created = _upload(client, world.bu_h).json()["created"][0]
    kavya = _person(client, world, created["username"])
    _make_bu_head(client, world, kavya["id"])
    assert _person(client, world, created["username"])["can_remove_bu_head"] is True

    def remove(person_id, headers=None):
        return client.post(
            f"{PEOPLE}/{person_id}/remove-bu-head", json={"confirm": True}, headers=headers or world.bu_h
        )

    assert remove(world.bu.id).status_code == 403  # never your own role
    assert _make_bu_head(client, world, world.bu.id).status_code == 403
    back = remove(kavya["id"])
    assert back.status_code == 200 and back.json()["role"] == "engineer"
    assert db.query(models.Notification).filter_by(notification_type="bu_head_removed").count() == 1

    # A BU Head created as one has no employee record to go back to.
    second = make_bu_head_account(db, "second.head")
    assert remove(second.id).status_code == 409


def test_the_last_bu_head_keeps_the_role(db):
    """With one active BU Head the role can't be removed (the rule behind the button)."""
    actor = make_bu_head_account(db, "actor.head")
    target = make_bu_head_account(db, "target.head", employee=True)
    target.is_active = False  # only the actor is active
    db.commit()

    with pytest.raises(ConflictError, match="at least one BU Head"):
        Provisioning(db).remove_bu_head(actor, target.id, True)


def make_bu_head_account(db, username, employee=False):
    employee_id = None
    if employee:
        record = models.Employee(employee_code=username.upper(), name=username, role_title="Director")
        db.add(record)
        db.flush()
        employee_id = record.id
    user = models.User(
        username=username, password_hash=NO_PASSWORD, full_name=username, role="bu_head", employee_id=employee_id
    )
    db.add(user)
    db.commit()
    return user


def test_a_bu_head_never_approves_their_own_hours(client, db, make, world, governed):
    project_id, node_a, _, pending = governed
    pending.reviewed_at = None
    db.commit()
    boss = db.get(models.User, world.bu.id)
    boss.employee_id = world.emp1.id  # as if Arjun had been promoted with hours still pending
    db.commit()

    response = client.post(f"/api/time-log-entries/{pending.id}/approve", headers=world.bu_h)

    assert response.status_code == 403
