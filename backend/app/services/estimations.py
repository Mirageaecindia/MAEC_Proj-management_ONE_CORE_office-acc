"""Project estimations (decided 2026-10-15): the BU Head's resourcing estimates, saved by name
and reopened later. The grid's rules (date columns, staff codes, hours) are in
app/domain/estimation.py.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, NotFoundError
from app.domain.estimation import STAFF_CODES, check_row, check_stages, column_dates, row_total
from app.repositories.estimations import EstimationRepository

NOT_FOUND = "That estimation no longer exists. Refresh the page."


@dataclass(frozen=True)
class EstimationRow:
    code: str
    role: str
    hours: dict[date, float]


@dataclass(frozen=True)
class EstimationData:
    name: str
    start_date: date
    end_date: date
    interval_days: int
    rows: list[EstimationRow]
    stages: dict[date, str] = field(default_factory=dict)  # the stage of a date column


class ProjectEstimations:
    def __init__(self, db: Session):
        self.db = db
        self.repository = EstimationRepository(db)

    @staticmethod
    def codes() -> list[dict]:
        """The staff codes a row can take, each with its role."""
        return [{"code": code, "role": role} for code, role in STAFF_CODES]

    def list(self) -> list[dict]:
        return [_summary(estimation) for estimation in self.repository.list()]

    def get(self, estimation_id: int) -> dict:
        return _detail(self._found(estimation_id))

    def create(self, user: models.User, data: EstimationData) -> dict:
        estimation = models.ProjectEstimation(created_by_user_id=user.id)
        _fill(estimation, data)
        self.repository.add(estimation)
        self.db.commit()
        self.db.refresh(estimation)
        return _detail(estimation)

    def update(self, estimation_id: int, data: EstimationData) -> dict:
        estimation = self._found(estimation_id)
        _fill(estimation, data)
        self.db.commit()
        self.db.refresh(estimation)
        return _detail(estimation)

    def delete(self, estimation_id: int) -> None:
        self.repository.delete(self._found(estimation_id))
        self.db.commit()

    def _found(self, estimation_id: int) -> models.ProjectEstimation:
        estimation = self.repository.get(estimation_id)
        if estimation is None:
            raise NotFoundError(NOT_FOUND)
        return estimation


def _fill(estimation: models.ProjectEstimation, data: EstimationData) -> None:
    """Check the whole grid, then store it: hours by ISO date, the empty ones left out."""
    name = data.name.strip()
    if not name:
        raise BadRequestError("Give the estimation a name.")
    try:
        columns = set(column_dates(data.start_date, data.end_date, data.interval_days))
        for row in data.rows:
            check_row(row.code, row.role, row.hours, columns, data.interval_days)
        check_stages(data.stages, columns)
    except ValueError as error:
        raise BadRequestError(str(error)) from None
    estimation.name = name
    estimation.start_date = data.start_date
    estimation.end_date = data.end_date
    estimation.interval_days = data.interval_days
    estimation.rows = [
        {
            "code": row.code,
            "role": row.role,
            "hours": {day.isoformat(): float(value) for day, value in sorted(row.hours.items()) if value},
        }
        for row in data.rows
    ]
    estimation.stages = {day.isoformat(): stage for day, stage in sorted(data.stages.items())}


def _summary(estimation: models.ProjectEstimation) -> dict:
    return {
        "id": estimation.id,
        "name": estimation.name,
        "start_date": estimation.start_date.isoformat(),
        "end_date": estimation.end_date.isoformat(),
        "interval_days": estimation.interval_days,
        "row_count": len(estimation.rows or []),
        "total_hours": round(sum(row_total(row["hours"]) for row in estimation.rows or []), 2),
        "updated_at": estimation.updated_at,
    }


def _detail(estimation: models.ProjectEstimation) -> dict:
    """The saved grid with its totals: each row's, each date column's, and the whole estimation's."""
    dates = [
        day.isoformat() for day in column_dates(estimation.start_date, estimation.end_date, estimation.interval_days)
    ]
    rows = [{**row, "total": row_total(row["hours"])} for row in estimation.rows or []]
    return {
        **_summary(estimation),
        "dates": dates,
        "rows": rows,
        "stages": estimation.stages or {},
        "column_totals": [round(sum(row["hours"].get(day, 0) for row in rows), 2) for day in dates],
        "created_at": estimation.created_at,
    }
