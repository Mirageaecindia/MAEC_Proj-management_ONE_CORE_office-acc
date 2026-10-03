"""Onboarding people and first-login passwords (app/services/provisioning.py, auth).

The BU Head uploads an HR export; everyone without an account gets an engineer
account named by their work email, with a temporary password that opens nothing
but the change-password screen until it is replaced.
"""

import io

import models
from factories import PASSWORD

IMPORT, RESET = "/api/people/import", "/api/people/reset-password"
LOGIN, ME, CHANGE = "/api/auth/login", "/api/auth/me", "/api/auth/change-password"

# Shaped like the real export: extra columns (phones), Windows encoding, non-breaking spaces.
HR_EXPORT = (
    "Employee Id,First Name,Last Name,Full Name,Work Email,Job Role,Work Phone Number,Personal Phone Number\r\n"
    "M0101,Kavya,Raman,Kavya Raman,Kavya.Raman@MirageAEC.com,Senior\xa0Electrical\xa0Engineer,044 1111,98400 11111\r\n"
    "M0102,Suresh,Babu,Suresh  Babu ,suresh.babu@mirageaec.com,BIM Modeller - PHE,044 2222,98400 22222\r\n"
).encode("cp1252")


def _upload(client, headers, content=HR_EXPORT, name="people.csv"):
    return client.post(IMPORT, files={"file": (name, io.BytesIO(content), "text/csv")}, headers=headers)


def _login(client, username, password):
    return client.post(LOGIN, json={"username": username, "password": password})


def _bearer(response):
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_the_bu_head_imports_engineers_with_their_own_temporary_passwords(client, db, world):
    response = _upload(client, world.bu_h)

    assert response.status_code == 200, response.text
    created = response.json()["created"]
    assert [(c["username"], c["full_name"], c["employee_code"]) for c in created] == [
        ("kavya.raman@mirageaec.com", "Kavya Raman", "M0101"),
        ("suresh.babu@mirageaec.com", "Suresh Babu", "M0102"),  # spaces cleaned
    ]
    passwords = [c["temporary_password"] for c in created]
    assert len(set(passwords)) == 2 and all(len(p) == 12 for p in passwords)
    assert response.json()["skipped"] == []

    kavya = db.query(models.User).filter_by(username="kavya.raman@mirageaec.com").one()
    employee = db.get(models.Employee, kavya.employee_id)
    assert (kavya.role, kavya.full_name, kavya.must_change_password) == ("engineer", "Kavya Raman", True)
    assert (employee.employee_code, employee.name, employee.role_title) == (
        "M0101",
        "Kavya Raman",
        "Senior Electrical Engineer",
    )
    assert passwords[0] not in kavya.password_hash  # stored only as a hash
    assert not hasattr(employee, "phone") and "98400" not in str(vars(employee))  # phones are never read


def test_a_temporary_password_opens_nothing_but_the_change_password_screen(client, world):
    created = _upload(client, world.bu_h).json()["created"][0]

    signed_in = _login(client, "KAVYA.RAMAN@mirageaec.com", created["temporary_password"])  # any case
    assert signed_in.status_code == 200 and signed_in.json()["must_change_password"] is True
    headers = _bearer(signed_in)
    assert client.get(ME, headers=headers).json()["must_change_password"] is True
    blocked = client.get("/api/projects", headers=headers)
    assert blocked.status_code == 403 and blocked.headers["X-Error-Code"] == "PASSWORD_CHANGE_REQUIRED"
    assert client.post("/api/subtask-tracking/heartbeat", headers=headers).status_code == 403

    changed = client.post(
        CHANGE,
        json={"current_password": created["temporary_password"], "new_password": "my own secret"},
        headers=headers,
    )

    assert changed.status_code == 200, changed.text
    assert client.get("/api/projects", headers=headers).status_code == 200  # this session carries on
    assert client.get(ME, headers=headers).json()["must_change_password"] is False
    assert _login(client, "kavya.raman@mirageaec.com", created["temporary_password"]).status_code == 401
    assert _login(client, "kavya.raman@mirageaec.com", "my own secret").json()["must_change_password"] is False


def test_changing_a_password_checks_the_current_one_and_ends_other_sessions(client, world):
    first, second = (_bearer(_login(client, world.engineer.username, PASSWORD)) for _ in range(2))

    def change(current, new):
        return client.post(CHANGE, json={"current_password": current, "new_password": new}, headers=first)

    assert change("wrong", "long enough").status_code == 400
    assert change(PASSWORD, "short").status_code == 400
    assert change(PASSWORD, PASSWORD).status_code == 400
    assert change(PASSWORD, "a brand new one").status_code == 200

    assert client.get(ME, headers=first).status_code == 200
    assert client.get(ME, headers=second).status_code == 401  # e.g. a browser left signed in elsewhere


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
        (3, "Employee M0202 already has an account."),
        (4, "Already has an account."),
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


def test_only_the_bu_head_imports_or_resets(client, world):
    assert _upload(client, world.eng_h).status_code == 403
    assert _upload(client, world.lead_h).status_code == 403  # a project lead is still an engineer account
    assert client.post(RESET, json={"username": world.engineer.username}, headers=world.lead_h).status_code == 403


def test_the_bu_head_resets_a_forgotten_password(client, db, world):
    old_session = _bearer(_login(client, world.engineer.username, PASSWORD))

    response = client.post(RESET, json={"username": world.engineer.username.upper()}, headers=world.bu_h)

    assert response.status_code == 200, response.text
    temporary = response.json()["temporary_password"]
    assert client.get(ME, headers=old_session).status_code == 401  # whoever had the old one is out
    assert _login(client, world.engineer.username, PASSWORD).status_code == 401
    again = _login(client, world.engineer.username, temporary)
    assert again.json()["must_change_password"] is True
    assert client.post(RESET, json={"username": world.bu.username}, headers=world.bu_h).status_code == 403
    assert client.post(RESET, json={"username": "nobody@mirageaec.com"}, headers=world.bu_h).status_code == 404


PEOPLE = "/api/people"


def _person(client, world, username):
    return next(p for p in client.get(PEOPLE, headers=world.bu_h).json() if p["username"] == username)


def test_the_bu_head_sees_everyone_with_an_account_but_never_a_password(client, world):
    _upload(client, world.bu_h)

    people = client.get(PEOPLE, headers=world.bu_h)

    assert people.status_code == 200, people.text
    kavya = next(p for p in people.json() if p["username"] == "kavya.raman@mirageaec.com")
    assert {k: kavya[k] for k in ("full_name", "employee_code", "job_role", "is_active", "must_change_password")} == {
        "full_name": "Kavya Raman",
        "employee_code": "M0101",
        "job_role": "Senior Electrical Engineer",
        "is_active": True,
        "must_change_password": True,  # hasn't signed in yet
    }
    assert (kavya["can_edit"], kavya["can_delete"]) == (True, True)  # nothing on record yet
    assert not any("password_hash" in p or "temporary_password" in p for p in people.json())
    bu_head = next(p for p in people.json() if p["role"] == "bu_head")
    assert (bu_head["can_edit"], bu_head["can_delete"]) == (False, False)
    assert client.get(PEOPLE, headers=world.lead_h).status_code == 403


def test_correcting_a_name_email_or_job_role(client, db, world, governed):
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
        "anita.k@mirageaec.com",
        "Electrical Lead",
    )
    db.expire_all()
    assert db.get(models.Project, project_id).project_lead_electrical == "Anita K."  # the copies follow
    assert db.get(models.WbsNode, node_a.id).assigned_lead == "Anita K."
    assert db.get(models.Employee, world.lead_e.employee_id).name == "Anita K."
    assert _login(client, "anita.k@mirageaec.com", PASSWORD).status_code == 200  # she signs in with the new email

    taken = client.patch(f"{PEOPLE}/{lead['id']}", json={"username": world.engineer.username}, headers=world.bu_h)
    assert taken.status_code == 409
    assert client.patch(f"{PEOPLE}/{lead['id']}", json={"full_name": "  "}, headers=world.bu_h).status_code == 400
    assert client.patch(f"{PEOPLE}/{lead['id']}", json={"username": "two words"}, headers=world.bu_h).status_code == 400
    bu_head = _person(client, world, world.bu.username)
    assert client.patch(f"{PEOPLE}/{bu_head['id']}", json={"full_name": "X"}, headers=world.bu_h).status_code == 403


def test_a_deactivated_person_is_signed_out_and_kept_on_record(client, db, world):
    session = _bearer(_login(client, world.engineer.username, PASSWORD))
    arjun = _person(client, world, world.engineer.username)

    off = client.post(f"{PEOPLE}/{arjun['id']}/deactivate", headers=world.bu_h)

    assert off.status_code == 200 and off.json()["is_active"] is False
    assert client.get(ME, headers=session).status_code == 401
    assert _login(client, world.engineer.username, PASSWORD).status_code == 401
    assert db.get(models.Employee, world.emp1.id) is not None
    on = client.post(f"{PEOPLE}/{arjun['id']}/reactivate", headers=world.bu_h)
    assert on.json()["is_active"] is True
    assert _login(client, world.engineer.username, PASSWORD).status_code == 200


def test_only_an_account_with_no_work_on_record_is_deleted(client, db, world, governed):
    created = _upload(client, world.bu_h).json()["created"][0]
    mistake = _person(client, world, created["username"])
    arjun = _person(client, world, world.engineer.username)  # booked, with hours: governed

    assert arjun["can_delete"] is False
    refused = client.delete(f"{PEOPLE}/{arjun['id']}", headers=world.bu_h)
    assert refused.status_code == 409 and "Deactivate the account instead" in refused.json()["detail"]

    assert client.delete(f"{PEOPLE}/{mistake['id']}", headers=world.bu_h).status_code == 200
    assert db.query(models.User).filter_by(username=created["username"]).count() == 0
    assert db.query(models.Employee).filter_by(employee_code="M0101").count() == 0
    assert _upload(client, world.bu_h).json()["created"][0]["username"] == created["username"]  # can come back
