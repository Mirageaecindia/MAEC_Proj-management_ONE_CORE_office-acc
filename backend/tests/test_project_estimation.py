"""Project estimation (2026-10-15): the BU Head's resourcing grid, made before a project exists.

Columns are dates from the start date every N days up to the end date; each row is a staff code
and its role, with hours per column date and a total; the estimation is saved by name.
"""

from datetime import date

import pytest

import models
from app.domain.estimation import MAX_COLUMNS, STAFF_CODES, STAGES, column_dates, column_limits

URL = "/api/estimations"


def grid(**overrides):
    payload = {
        "name": "DCH A9 tender",
        "start_date": "2027-01-01",
        "end_date": "2027-02-01",
        "interval_days": 7,
        "rows": [
            {"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-01": 9, "2027-01-15": 22}},
            {"code": "BE", "role": "BIM Modeller-E", "hours": {"2027-01-08": 27, "2027-01-29": 18}},
            {"code": "BE", "role": "BIM Modeller-E", "hours": {"2027-01-29": 9}},  # a second one
        ],
        "stages": {"2027-01-01": "CD", "2027-01-08": "CD", "2027-01-22": "SD"},  # 15 and 29 Jan: none chosen
    }
    return payload | overrides


def test_the_columns_are_the_start_date_then_every_n_days_up_to_the_end_date():
    jan = [date(2027, 1, day) for day in (1, 8, 15, 22, 29)]
    assert column_dates(date(2027, 1, 1), date(2027, 2, 1), 7) == jan
    assert column_dates(date(2027, 1, 1), date(2027, 1, 29), 7) == jan  # the end date itself when it falls on one
    assert column_dates(date(2027, 1, 1), date(2027, 1, 1), 7) == [date(2027, 1, 1)]
    assert len(column_dates(date(2027, 1, 1), date(2027, 1, 31), 1)) == 31
    with pytest.raises(ValueError):
        column_dates(date(2027, 2, 1), date(2027, 1, 1), 7)  # ends before it starts
    with pytest.raises(ValueError):
        column_dates(date(2027, 1, 1), date(2040, 1, 1), 1)  # thousands of columns
    assert MAX_COLUMNS >= 260  # five years week by week fit


def test_the_codes_are_the_resourcing_sheets_with_their_roles(client, world):
    codes = client.get(f"{URL}/codes", headers=world.bu_h).json()

    assert len(codes) == len(STAFF_CODES) == 28
    assert {"code": "SME", "role": "Senior Mechanical Engineer"} in codes
    assert [c["role"] for c in codes if c["code"] == "BL"] == ["BIM Manager", "BIM Coordinator"]  # one code, two roles


def test_the_bu_head_saves_an_estimation_and_reopens_it_with_its_totals(client, world):
    created = client.post(URL, json=grid(), headers=world.bu_h)

    assert created.status_code == 201, created.text
    estimation = client.get(f"{URL}/{created.json()['id']}", headers=world.bu_h).json()
    assert estimation["dates"] == ["2027-01-01", "2027-01-08", "2027-01-15", "2027-01-22", "2027-01-29"]
    assert [row["total"] for row in estimation["rows"]] == [31, 45, 9]
    assert estimation["column_totals"] == [9, 27, 22, 0, 27]
    assert estimation["total_hours"] == 85
    assert estimation["rows"][0]["hours"] == {"2027-01-01": 9, "2027-01-15": 22}

    listed = client.get(URL, headers=world.bu_h).json()
    assert [(e["name"], e["row_count"], e["total_hours"]) for e in listed] == [("DCH A9 tender", 3, 85)]


def test_editing_saves_the_whole_grid_again(client, world):
    estimation_id = client.post(URL, json=grid(), headers=world.bu_h).json()["id"]
    rows = [{"code": "BL", "role": "BIM Coordinator", "hours": {"2027-01-01": 10, "2027-01-15": 0}}]

    edited = client.put(
        f"{URL}/{estimation_id}",
        json=grid(name="DCH A9 R01", interval_days=14, rows=rows, stages={"2027-01-15": "SD"}),
        headers=world.bu_h,
    )

    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["name"], body["dates"]) == ("DCH A9 R01", ["2027-01-01", "2027-01-15", "2027-01-29"])
    assert body["rows"] == [
        {"code": "BL", "role": "BIM Coordinator", "hours": {"2027-01-01": 10.0}, "total": 10.0}
    ]  # an empty cell is not stored


def test_deleting_removes_it(client, world):
    estimation_id = client.post(URL, json=grid(), headers=world.bu_h).json()["id"]

    assert client.delete(f"{URL}/{estimation_id}", headers=world.bu_h).status_code == 200
    assert client.get(f"{URL}/{estimation_id}", headers=world.bu_h).status_code == 404
    assert client.get(URL, headers=world.bu_h).json() == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"name": "  "}, "name"),
        ({"end_date": "2026-12-01"}, "end date"),
        ({"rows": [{"code": "XYZ", "role": "Nobody", "hours": {}}]}, "staff codes"),
        ({"rows": [{"code": "SME", "role": "BIM Manager", "hours": {}}]}, "staff codes"),  # role of another code
        ({"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-02": 8}}]}, "date columns"),
        ({"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-08": -1}}]}, "at most 45"),
        (
            {"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-08": 46}}]},
            "at most 45 (5 working days x 9 h)",
        ),  # Fri to Thu
        (
            {"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-08": 7.5}}]},
            "whole hours",
        ),
    ],
)
def test_a_wrong_grid_is_refused_and_says_why(client, world, change, message):
    response = client.post(URL, json=grid(**change), headers=world.bu_h)

    assert response.status_code == 400, response.text
    assert message in response.json()["detail"]


def test_only_the_bu_head_estimates(client, world):
    estimation_id = client.post(URL, json=grid(), headers=world.bu_h).json()["id"]

    for headers in (world.lead_h, world.eng_h):
        assert client.get(URL, headers=headers).status_code == 403
        assert client.get(f"{URL}/codes", headers=headers).status_code == 403
        assert client.post(URL, json=grid(), headers=headers).status_code == 403
        assert client.put(f"{URL}/{estimation_id}", json=grid(), headers=headers).status_code == 403
        assert client.delete(f"{URL}/{estimation_id}", headers=headers).status_code == 403


def test_saving_an_estimation_is_in_the_audit_log(client, world):
    client.post(URL, json=grid(), headers=world.bu_h)

    latest = client.get("/api/audit/mine", headers=world.bu_h).json()["events"][0]
    assert latest["summary"] == "Created a project estimation"


def test_each_date_column_takes_a_stage_or_none(client, world):
    assert STAGES == ("CD", "SD", "DD", "TD", "IFC")
    estimation_id = client.post(URL, json=grid(), headers=world.bu_h).json()["id"]

    estimation = client.get(f"{URL}/{estimation_id}", headers=world.bu_h).json()
    assert estimation["stages"] == {"2027-01-01": "CD", "2027-01-08": "CD", "2027-01-22": "SD"}

    stages = {"2027-01-01": "TD", "2027-01-29": "IFC"}
    edited = client.put(f"{URL}/{estimation_id}", json=grid(stages=stages), headers=world.bu_h).json()
    assert edited["stages"] == stages


@pytest.mark.parametrize(
    ("stages", "message"),
    [({"2027-01-08": "XD"}, "not a stage"), ({"2027-01-09": "CD"}, "date columns")],
)
def test_a_wrong_stage_is_refused(client, world, stages, message):
    response = client.post(URL, json=grid(stages=stages), headers=world.bu_h)

    assert response.status_code == 400, response.text
    assert message in response.json()["detail"]


def test_an_estimation_saved_before_stages_has_none(client, db, world):
    estimation_id = client.post(URL, json=grid(stages={}), headers=world.bu_h).json()["id"]
    db.get(models.ProjectEstimation, estimation_id).stages = None  # as migration 0026 leaves the older ones
    db.commit()

    assert client.get(f"{URL}/{estimation_id}", headers=world.bu_h).json()["stages"] == {}


def test_a_column_holds_9_hours_for_each_working_day_it_covers():
    friday, monday = date(2027, 1, 1), date(2027, 1, 4)
    # Every 2 days from a Friday: Fri+Sat, Sun+Mon, then Tue alone (the end date): 9 each.
    assert column_limits(friday, date(2027, 1, 5), 2) == {friday: 9, date(2027, 1, 3): 9, date(2027, 1, 5): 9}
    assert column_limits(monday, date(2027, 1, 8), 2)[monday] == 18  # Mon+Tue
    assert column_limits(friday, date(2027, 2, 1), 7)[friday] == 45  # Fri, then Mon to Thu
    assert column_limits(friday, date(2027, 2, 1), 7)[date(2027, 1, 29)] == 18  # the last: Fri 29 Jan, Mon 1 Feb
    assert column_limits(date(2027, 1, 2), date(2027, 1, 4), 1) == {  # Sat, Sun, Mon
        date(2027, 1, 2): 0,
        date(2027, 1, 3): 0,
        date(2027, 1, 4): 9,
    }


@pytest.mark.parametrize(
    ("start", "end", "interval", "day", "hours", "allowed"),
    [
        ("2027-01-04", "2027-01-10", 2, "2027-01-04", 18, True),  # Mon+Tue: 18 is the most
        ("2027-01-04", "2027-01-10", 2, "2027-01-04", 19, False),
        ("2027-01-01", "2027-01-05", 2, "2027-01-01", 9, True),  # Fri+Sat: the weekend doesn't count
        ("2027-01-01", "2027-01-05", 2, "2027-01-01", 10, False),
        ("2027-01-02", "2027-01-04", 1, "2027-01-02", 1, False),  # a Saturday alone: no hours
    ],
)
def test_hours_are_refused_past_the_working_days_of_their_column(
    client, world, start, end, interval, day, hours, allowed
):
    rows = [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {day: hours}}]
    payload = grid(start_date=start, end_date=end, interval_days=interval, rows=rows, stages={})

    response = client.post(URL, json=payload, headers=world.bu_h)

    assert response.status_code == (201 if allowed else 400), response.text
    if day == "2027-01-02":
        assert "weekend" in response.json()["detail"]
