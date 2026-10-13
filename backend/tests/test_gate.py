"""MAEC One's gate (app/api/gate.py, app/api/proxy.py) and who the person is here (app/core/identity.py).

Core is faked in-process (fakes.FakeCore, conftest's `core`): it answers in the real check's
order. Nobody signs in to this app; every request asks Core, and nothing is cached.
"""

import httpx
import pytest

import models
from app.api import gate, proxy
from app.core.config import GATE_SECRET_PLACEHOLDER, GateConfigError, Settings, require_gate_settings

ME, PROJECTS = "/api/auth/me", "/api/projects"
GOOD_SECRET = "s" * 32


# -- the gate: Core decides who gets in ------------------------------------------------------


def test_without_maec_one_s_cookie_the_answer_is_401_with_where_to_sign_in(client, core):
    response = client.get(ME)

    assert response.status_code == 401
    body = response.json()
    assert body["reason"] == "not_signed_in"
    assert body["login_url"] == "http://auth.test/?next=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Fme"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Cookie" in response.headers["Vary"]


def test_core_down_is_503_never_a_pass(client, core, world):
    core.down = True

    for response in (client.get(ME, headers=world.bu_h), client.post(PROJECTS, json={}, headers=world.bu_h)):
        assert response.status_code == 503
        assert response.json()["detail"] == "MAEC One is unavailable"


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"permissions": []}),  # no user
        httpx.Response(302, headers={"Location": "/"}),
    ],
)
def test_any_other_answer_from_core_is_503(client, world, answer):
    gate.transport = httpx.MockTransport(lambda request: answer)
    gate.reset_client()

    assert client.get(ME, headers=world.bu_h).status_code == 503


def test_core_slower_than_three_seconds_is_503(client, world):
    def slow(request):
        raise httpx.ReadTimeout("no answer within the timeout", request=request)

    gate.transport = httpx.MockTransport(slow)
    gate.reset_client()

    assert gate.TIMEOUT_SECONDS == 3.0
    assert client.get(ME, headers=world.bu_h).status_code == 503


def test_the_gate_sends_core_the_app_its_secret_the_url_method_origin_and_raw_cookie(client, core, world):
    client.post(
        PROJECTS, json=world.project_payload(), headers={**world.bu_h, "Cookie": world.bu_h["Cookie"] + "; other=1"}
    )

    sent = core.calls[-1]
    assert sent["x-maec-app"] == "projects"
    assert sent["x-maec-gate-secret"] == "test-gate-secret-" + "x" * 32
    assert sent["x-original-url"] == "http://testserver/api/projects"
    assert sent["x-original-method"] == "POST"
    assert sent["x-original-origin"] == "http://testserver"
    assert sent["cookie"].endswith("; other=1")  # the browser's Cookie header, as received


def test_a_change_from_a_foreign_origin_is_refused_and_changes_nothing(client, db, world):
    payload = world.project_payload()

    forged = client.post(PROJECTS, json=payload, headers={**world.bu_h, "Origin": "https://evil.mirageaec.com"})
    no_origin = client.post(PROJECTS, json=payload, headers={"Cookie": world.bu_h["Cookie"]})

    for response in (forged, no_origin):
        assert response.status_code == 403 and response.json()["reason"] == "bad_origin"
    assert db.query(models.Project).count() == 0
    assert client.post(PROJECTS, json=payload, headers=world.bu_h).status_code == 201  # from the app itself


def test_a_revoked_seat_or_a_sign_out_bites_on_the_very_next_request(client, core, make, world):
    token = core.sign_in(world.engineer.username, core_id="core-arjun")
    arjun = core.headers(token)
    assert client.get(ME, headers=arjun).status_code == 200

    core.seats.discard("core-arjun")
    refused = client.get(ME, headers=arjun)
    assert refused.status_code == 403 and refused.json()["reason"] == "no_access"

    core.seats.add("core-arjun")
    core.sign_out(token)
    assert client.get(ME, headers=arjun).status_code == 401


def test_only_the_health_probe_answers_without_asking_core(client, core):
    core.down = True

    response = client.get("/health")

    assert response.status_code == 200 and "Cookie" not in response.headers.get("Vary", "")
    assert core.calls == []


# -- who the person is here -----------------------------------------------------------------


def test_the_first_visit_links_the_profile_by_email_and_later_visits_use_the_link(client, db, core, make):
    kavya = make.user(" Kavya.Raman@MirageAEC.com", "engineer", "Kavya Raman")  # case and spaces ignored
    first = core.headers(core.sign_in("kavya.raman@mirageaec.com", "Kavya R.", core_id="core-k"))

    me = client.get(ME, headers=first)

    assert me.status_code == 200 and me.json()["id"] == kavya.id
    db.refresh(kavya)
    assert kavya.core_user_id == "core-k"
    assert (kavya.full_name, kavya.role) == ("Kavya Raman", "engineer")  # Core's name never replaces this app's

    kavya.username = "renamed.locally@mirageaec.com"  # the email no longer matches: the link alone finds her
    db.commit()
    assert client.get(ME, headers=first).json()["id"] == kavya.id


def test_an_email_change_in_core_keeps_the_link(client, db, core, make):
    kavya = make.user("kavya@mirageaec.com", "engineer", "Kavya Raman")
    client.get(ME, headers=core.headers(core.sign_in("kavya@mirageaec.com", core_id="core-k")))
    other = make.user("kavya.r@mirageaec.com", "engineer", "Another Kavya")  # someone already has the new address

    after = client.get(ME, headers=core.headers(core.sign_in("kavya.r@mirageaec.com", core_id="core-k")))

    assert after.status_code == 200 and after.json()["id"] == kavya.id  # by core_user_id, not the new email
    db.refresh(other)
    assert other.core_user_id is None


def test_someone_with_a_seat_but_no_profile_is_told_to_ask_a_business_head(client, db, core, world):
    """Not created automatically: an employee record needs the HR code and job role (B2)."""
    users_before = db.query(models.User).count()
    stranger = core.headers(core.sign_in("new.joiner@mirageaec.com", "New Joiner"))

    for response in (client.get(ME, headers=stranger), client.get(PROJECTS, headers=stranger)):
        assert response.status_code == 403
        assert response.headers["X-Error-Code"] == "PROFILE_NOT_SET_UP"
        assert (
            response.json()["detail"] == "Your Project Management profile hasn't been set up yet. Ask a Business Head."
        )
    assert db.query(models.User).count() == users_before
    assert db.query(models.Employee).filter_by(name="New Joiner").count() == 0


def test_a_profile_linked_to_another_core_account_is_never_taken_over_by_email(client, db, core, make):
    kavya = make.user("kavya@mirageaec.com", "engineer", "Kavya Raman")
    client.get(ME, headers=core.headers(core.sign_in("kavya@mirageaec.com", core_id="core-k")))

    impostor = client.get(ME, headers=core.headers(core.sign_in("KAVYA@mirageaec.com", core_id="core-new")))

    assert impostor.status_code == 403 and impostor.headers["X-Error-Code"] == "PROFILE_NOT_SET_UP"
    db.refresh(kavya)
    assert kavya.core_user_id == "core-k"


def test_two_profiles_with_the_same_email_link_neither(client, db, core, make):
    make.user("dup@mirageaec.com", "engineer", "One")
    make.user("DUP@mirageaec.com", "engineer", "Two")  # the old unique index ignored case

    response = client.get(ME, headers=core.headers(core.sign_in("dup@mirageaec.com", core_id="core-d")))

    assert response.status_code == 403 and "More than one" in response.json()["detail"]
    assert db.query(models.User).filter(models.User.core_user_id.is_not(None)).count() == 0


def test_a_deactivated_profile_is_refused_whatever_core_says(client, db, world):
    world.engineer.is_active = False
    db.commit()

    response = client.get(ME, headers=world.eng_h)

    assert response.status_code == 403 and response.headers["X-Error-Code"] == "PROFILE_INACTIVE"


def test_me_returns_the_local_profile_leads_projects_and_where_maec_one_is(client, world):
    me = client.get(ME, headers=world.lead_h).json()

    assert me == {
        "id": world.lead_e.id,
        "username": world.lead_e.username,
        "full_name": "Anita Kumar",
        "role": "engineer",
        "employee_id": world.lead_e.employee_id,
        "leads_projects": False,
        "core_url": "http://auth.test",
    }


# -- this app's rules are unchanged -----------------------------------------------------------


def test_roles_and_project_leads_stay_this_app_s_rules(client, core, world):
    """Core says only who the person is; bu_head, engineer and per-project lead come from here."""
    project_id = world.create_project()["id"]  # the BU Head creates; Anita leads it
    booking = {
        "employee_id": world.emp1.id,
        "utilization_rate": 50,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }

    assert client.post(PROJECTS, json=world.project_payload(), headers=world.eng_h).status_code == 403
    assert client.post(PROJECTS, json=world.project_payload(), headers=world.lead_h).status_code == 403
    assert client.get("/api/people", headers=world.lead_h).status_code == 403
    assert (
        client.post(f"/api/projects/{project_id}/resource-bookings", json=booking, headers=world.eng_h).status_code
        == 403
    )
    assert (
        client.post(f"/api/projects/{project_id}/resource-bookings", json=booking, headers=world.lead_h).status_code
        == 200
    )
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.lead_h).status_code == 403
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    assert client.get(f"/api/projects/{project_id}", headers=world.other_lead_h).status_code == 403  # not his project
    roles = {p["id"]: p["my_role"] for p in client.get(PROJECTS, headers=world.lead_h).json()}
    assert roles[project_id] == "lead"
    assert client.get(f"/api/projects/{project_id}", headers=world.eng_h).json()["my_role"] == "engineer"


# -- settings and the proxy -------------------------------------------------------------------


def _settings(**overrides):
    values = {"core_url": "http://maec-core:8000", "core_public_url": "https://auth.mirageaec.com",
              "maec_app_key": "projects", "maec_gate_secret": GOOD_SECRET}  # fmt: skip
    return Settings(_env_file=None, **{**values, **overrides})


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"core_url": ""}, "CORE_URL is not set"),
        ({"core_public_url": ""}, "CORE_PUBLIC_URL is not set"),
        ({"maec_app_key": ""}, "MAEC_APP_KEY is not set"),
        ({"maec_gate_secret": ""}, "MAEC_GATE_SECRET is not set"),
        ({"maec_gate_secret": GATE_SECRET_PLACEHOLDER}, "still the placeholder"),
        ({"maec_gate_secret": "s" * 31}, "shorter than 32 characters"),
    ],
)
def test_the_app_refuses_to_start_without_usable_gate_settings(override, says):
    with pytest.raises(GateConfigError, match=says):
        require_gate_settings(_settings(**override))


def test_good_gate_settings_start():
    require_gate_settings(_settings())


def test_trusted_proxies_may_not_be_everyone(monkeypatch):
    proxy._parse.cache_clear()
    monkeypatch.setattr(proxy, "get_settings", lambda: _settings(trusted_proxies="10.231.3.0/24, *"))

    with pytest.raises(proxy.ProxyConfigError):
        proxy.check()


def test_forwarded_scheme_and_host_are_believed_only_from_a_trusted_proxy(client, core, world, monkeypatch):
    forwarded = {**world.bu_h, "X-Forwarded-Proto": "https", "X-Forwarded-Host": "pm.mirageaec.com"}

    client.get(ME, headers=forwarded)  # the test client's peer is not trusted
    assert core.calls[-1]["x-original-url"] == "http://testserver/api/auth/me"

    monkeypatch.setattr(proxy, "get_settings", lambda: _settings(trusted_proxies="testclient"))
    client.get(ME, headers=forwarded)
    assert core.calls[-1]["x-original-url"] == "https://pm.mirageaec.com/api/auth/me"

    client.get(ME, headers={**forwarded, "X-Forwarded-Host": "evil.example/path"})  # not a host: not applied
    assert core.calls[-1]["x-original-url"] == "https://testserver/api/auth/me"
