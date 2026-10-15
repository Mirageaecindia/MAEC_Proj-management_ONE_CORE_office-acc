"""Project estimation (2026-10-15): the BU Head's resourcing grid, made before a project exists.

Columns are dates from the start date every N days up to the end date; each row is a staff code
and its role, with hours per column date and a total; the estimation is saved by name.
"""

from datetime import date

import pytest

from app.domain.estimation import MAX_COLUMNS, STAFF_CODES, column_dates

URL = "/api/estimations"


def grid(**overrides):
    payload = {
        "name": "DCH A9 tender",
        "start_date": "2027-01-01",
        "end_date": "2027-02-01",
        "interval_days": 7,
        "rows": [
            {"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-01": 9, "2027-01-15": 22.5}},
            {"code": "BE", "role": "BIM Modeller-E", "hours": {"2027-01-08": 27, "2027-01-29": 18}},
            {"code": "BE", "role": "BIM Modeller-E", "hours": {"2027-01-29": 9}},  # a second one
        ],
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
    assert [row["total"] for row in estimation["rows"]] == [31.5, 45, 9]
    assert estimation["column_totals"] == [9, 27, 22.5, 0, 27]
    assert estimation["total_hours"] == 85.5
    assert estimation["rows"][0]["hours"] == {"2027-01-01": 9.0, "2027-01-15": 22.5}

    listed = client.get(URL, headers=world.bu_h).json()
    assert [(e["name"], e["row_count"], e["total_hours"]) for e in listed] == [("DCH A9 tender", 3, 85.5)]


def test_editing_saves_the_whole_grid_again(client, world):
    estimation_id = client.post(URL, json=grid(), headers=world.bu_h).json()["id"]
    rows = [{"code": "BL", "role": "BIM Coordinator", "hours": {"2027-01-01": 10, "2027-01-15": 0}}]

    edited = client.put(
        f"{URL}/{estimation_id}", json=grid(name="DCH A9 R01", interval_days=14, rows=rows), headers=world.bu_h
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
        ({"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-08": -1}}]}, "between 0"),
        ({"rows": [{"code": "SME", "role": "Senior Mechanical Engineer", "hours": {"2027-01-08": 169}}]}, "168"),
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
