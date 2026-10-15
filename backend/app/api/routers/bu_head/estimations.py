"""Project estimation (BU Head): resourcing estimates made before a project exists, saved by name.

The rules are in app/services/estimations.py and app/domain/estimation.py.
"""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import models
from app.api.deps import get_estimation_service
from app.core.security import require_bu_head
from app.domain.estimation import MAX_ROWS
from app.services.estimations import EstimationData, EstimationRow, ProjectEstimations

router = APIRouter(prefix="/estimations", tags=["project estimation"])


class EstimationRowIn(BaseModel):
    code: str = Field(max_length=20)
    role: str = Field(max_length=100)
    hours: dict[date, float] = {}  # hours per column date


class EstimationIn(BaseModel):
    name: str = Field(max_length=200)
    start_date: date
    end_date: date
    interval_days: int = Field(ge=1, le=366)
    rows: list[EstimationRowIn] = Field(default=[], max_length=MAX_ROWS)
    stages: dict[date, str] = {}  # the design stage of a date column (CD, SD, DD, TD or IFC)

    def data(self) -> EstimationData:
        rows = [EstimationRow(row.code, row.role, row.hours) for row in self.rows]
        return EstimationData(self.name, self.start_date, self.end_date, self.interval_days, rows, self.stages)


@router.get("/codes")
def list_codes(_user: models.User = Depends(require_bu_head)) -> list[dict]:
    """The staff codes a row can take, each with its role."""
    return ProjectEstimations.codes()


@router.get("")
def list_estimations(
    _user: models.User = Depends(require_bu_head),
    service: ProjectEstimations = Depends(get_estimation_service),
) -> list[dict]:
    return service.list()


@router.post("", status_code=201)
def create_estimation(
    payload: EstimationIn,
    user: models.User = Depends(require_bu_head),
    service: ProjectEstimations = Depends(get_estimation_service),
) -> dict:
    return service.create(user, payload.data())


@router.get("/{estimation_id}")
def get_estimation(
    estimation_id: int,
    _user: models.User = Depends(require_bu_head),
    service: ProjectEstimations = Depends(get_estimation_service),
) -> dict:
    return service.get(estimation_id)


@router.put("/{estimation_id}")
def update_estimation(
    estimation_id: int,
    payload: EstimationIn,
    _user: models.User = Depends(require_bu_head),
    service: ProjectEstimations = Depends(get_estimation_service),
) -> dict:
    """The whole grid, as the page holds it: hours outside the new date columns must be left out."""
    return service.update(estimation_id, payload.data())


@router.delete("/{estimation_id}")
def delete_estimation(
    estimation_id: int,
    _user: models.User = Depends(require_bu_head),
    service: ProjectEstimations = Depends(get_estimation_service),
) -> dict:
    service.delete(estimation_id)
    return {"ok": True, "deleted_estimation_id": estimation_id}
