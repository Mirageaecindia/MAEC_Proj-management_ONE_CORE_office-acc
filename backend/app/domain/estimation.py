"""Project estimation (decided 2026-10-15): the BU Head's resourcing estimate for a project, made
before the project exists, in the layout of the company's resourcing sheet ("Mastersheet-Projects").

The columns are dates: the start date, then every `interval_days` days, up to the end date. Under
the dates, each column can name the design stage it falls in (the sheet's stage row). Each row is a
staff code with its role, and the hours planned for it on each column date; its total is the sum of
its hours. The same code can be on several rows (two BIM Modellers, say).
"""

from datetime import date, timedelta

# Staff codes and roles, as on the resourcing sheet (Mastersheet-Projects, B2:C35). One code can
# name more than one role (BL: BIM Manager or BIM Coordinator), so a row picks the pair.
STAFF_CODES: tuple[tuple[str, str], ...] = (
    ("MEP", "MEP Director"),
    ("LMEP", "MEP Lead (Dubai)"),
    ("LME", "Lead Mech Engr (Dubai)"),
    ("LPE", "Lead PHE Engr (Dubai)"),
    ("LEE", "Lead Elect Engr (Dubai)"),
    ("SMED", "Senior Mech Engr-Dubai"),
    ("SPED", "Senior PHE Engr-Dubai"),
    ("SEED", "Senior Elect Engr-Dubai"),
    ("AME", "Principal Mech Engr"),
    ("APE", "Principal PHE Engr"),
    ("AEE", "Principal Elect Engr/Director"),
    ("SPE", "Senior PHE Engr"),
    ("SEE", "Senior Electrical Engineer"),
    ("SME", "Senior Mechanical Engineer"),
    ("JME", "Mechanical Engineer"),
    ("JEE", "Electrical Engineer"),
    ("JPE", "PHE Engineer"),
    ("BL", "BIM Manager"),
    ("BL", "BIM Coordinator"),
    ("BPL", "BIM Lead-P"),
    ("BEL", "BIM Lead-E"),
    ("BML", "BIM Lead-M"),
    ("BM", "BIM Modeller-M"),
    ("BP", "BIM Modeller-P"),
    ("BE", "BIM Modeller-E"),
    ("BJM", "Junior BIM Modeller-M"),
    ("BJE", "Junior BIM Modeller-E"),
    ("BJP", "Junior BIM Modeller-P"),
)

# The design stage a date column falls in, chosen per column (or left empty).
STAGES = ("CD", "SD", "DD", "TD", "IFC")

HOURS_PER_DAY = 9  # what one person works on a working day (Monday to Friday)
MAX_COLUMNS = 400  # e.g. eight years week by week: more is a typo in a date
MAX_ROWS = 300


def column_dates(start: date, end: date, interval_days: int) -> list[date]:
    """The grid's columns: the start date, then every `interval_days` days, up to the end date.
    1 Jan to 1 Feb every 7 days: 1, 8, 15, 22 and 29 Jan."""
    if interval_days < 1:
        raise ValueError("The number of days between columns must be at least 1.")
    if end < start:
        raise ValueError("The end date must be on or after the start date.")
    count = (end - start).days // interval_days + 1
    if count > MAX_COLUMNS:
        raise ValueError(
            f"That makes {count} date columns; at most {MAX_COLUMNS}. "
            "Check the dates or space the columns further apart."
        )
    return [start + timedelta(days=interval_days * n) for n in range(count)]


def working_days(first: date, last: date) -> int:
    """Monday to Friday from `first` to `last`, both included (the app's weekend is Saturday and Sunday)."""
    return sum(1 for offset in range((last - first).days + 1) if (first + timedelta(days=offset)).weekday() < 5)


def column_limits(start: date, end: date, interval_days: int) -> dict[date, int]:
    """The most hours one person can have in each date column: HOURS_PER_DAY for each working
    day the column covers, from its date to the day before the next column (the last column:
    to the end date). Every 2 days from a Monday: 18; from a Friday: 9 (Saturday doesn't count)."""
    limits = {}
    for day in column_dates(start, end, interval_days):
        last = min(day + timedelta(days=interval_days - 1), end)
        limits[day] = HOURS_PER_DAY * working_days(day, last)
    return limits


def check_row(code: str, role: str, hours: dict[date, float], limits: dict[date, int]) -> None:
    """A row is a known code and role, and whole hours only on column dates, from 0 up to the
    column's limit (column_limits)."""
    if (code, role) not in STAFF_CODES:
        raise ValueError(f"'{code} - {role}' is not one of the staff codes.")
    for day, value in hours.items():
        if day not in limits:
            raise ValueError(f"{code}: {day.isoformat()} is not one of the date columns.")
        if value != int(value):
            raise ValueError(f"{code}: {value} hours on {day.isoformat()}; enter whole hours.")
        most = limits[day]
        if value < 0 or value > most:
            days = most // HOURS_PER_DAY
            reason = (
                "it has no working day (weekend)"
                if days == 0
                else f"at most {most} ({days} working day{'s' if days > 1 else ''} x {HOURS_PER_DAY} h)"
            )
            raise ValueError(f"{code}: {value:g} hours on {day.isoformat()}; {reason}.")


def check_stages(stages: dict[date, str], columns: set[date]) -> None:
    """Each stage is one of STAGES, on a column date."""
    for day, stage in stages.items():
        if day not in columns:
            raise ValueError(f"The stage on {day.isoformat()} is not on one of the date columns.")
        if stage not in STAGES:
            raise ValueError(f"'{stage}' is not a stage; choose one of {', '.join(STAGES)}.")


def row_total(hours: dict) -> float:
    return round(sum(hours.values()), 2)
