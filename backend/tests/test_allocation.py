"""Capacity is checked per day: the busiest day stays at or below 100% (TODO N12)."""

from datetime import date

import pytest

from app.domain.allocation import peak_allocation

JAN, FEB, MAR = (date(2027, m, 1) for m in (1, 2, 3))
JAN_END, FEB_END, MAR_END = date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)


@pytest.mark.parametrize(
    ("bookings", "window", "expected"),
    [
        ([(JAN, JAN_END, 60), (MAR, MAR_END, 60)], (JAN, MAR_END), 60),  # never on the same day
        ([(JAN, FEB_END, 50), (FEB, MAR_END, 30)], (JAN, MAR_END), 80),  # overlap in February
        # The backlog's example: three 50% bookings, but at most two on any one day.
        ([(JAN, MAR_END, 50), (FEB, FEB_END, 50), (MAR, MAR_END, 50)], (JAN, MAR_END), 100),
        ([(JAN, JAN_END, 40), (JAN_END, FEB_END, 40)], (JAN, FEB_END), 80),  # end dates are inclusive
        ([(None, None, 30), (FEB, FEB_END, 50)], (MAR, MAR_END), 30),  # undated = open-ended
        ([(JAN, JAN_END, 90)], (FEB, MAR_END), 0),  # outside the window
    ],
)
def test_peak_allocation_is_the_busiest_day(bookings, window, expected):
    assert peak_allocation(bookings, *window) == expected


def _book(client, world, project_id, pct, start, end):
    return client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={"employee_id": world.emp1.id, "utilization_rate": pct, "start_date": start, "end_date": end},
        headers=world.lead_h,
    )


def test_bookings_in_different_months_can_each_use_most_of_the_capacity(client, world):
    tower, mall = world.create_project()["id"], world.create_project()["id"]

    assert _book(client, world, tower, 60, "2027-01-01", "2027-01-31").status_code == 200
    assert _book(client, world, mall, 60, "2027-03-01", "2027-03-31").status_code == 200


def test_overlapping_bookings_above_100_percent_are_refused(client, world):
    tower, mall = world.create_project()["id"], world.create_project()["id"]
    _book(client, world, tower, 60, "2027-01-01", "2027-02-28")

    refused = _book(client, world, mall, 60, "2027-02-15", "2027-03-31")

    assert refused.status_code == 400
    assert refused.headers["X-Error-Code"] == "ALLOCATION_LIMIT"
    assert "already allocated 60%" in refused.json()["detail"]
    assert _book(client, world, mall, 40, "2027-02-15", "2027-03-31").status_code == 200


def test_editing_a_booking_checks_its_new_dates(client, world):
    tower, mall = world.create_project()["id"], world.create_project()["id"]
    _book(client, world, tower, 60, "2027-01-01", "2027-01-31")
    booking_id = _book(client, world, mall, 60, "2027-03-01", "2027-03-31").json()["id"]

    moved = client.put(
        f"/api/projects/{mall}/resource-bookings/{booking_id}",
        json={"start_date": "2027-01-15"},
        headers=world.lead_h,
    )

    assert moved.status_code == 400  # now overlaps January's 60%
