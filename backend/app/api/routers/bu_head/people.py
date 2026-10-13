"""People (BU Head): profiles in this app, from an HR export or one at a time; list, correct, BU Head role.

Signing in, passwords and access (a seat, deactivating a leaver) are managed in MAEC One
Core since the move to MAEC One (decided 2026-10-13). The rules are in
app/services/provisioning.py.
"""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

import models
from app.api.deps import get_provisioning
from app.core.errors import BadRequestError
from app.core.security import require_bu_head
from app.services.provisioning import Provisioning, read_people

router = APIRouter(prefix="/people", tags=["people"])

MAX_FILE_BYTES = 1_000_000  # an HR export of a few hundred people is a few kilobytes


class RoleChangeIn(BaseModel):
    """The BU Head confirmed the role change in a dialog."""

    confirm: bool = False


class PersonIn(BaseModel):
    """One person, as a row of the HR export."""

    employee_code: str = Field(max_length=50)
    full_name: str = Field(max_length=150)
    email: str = Field(max_length=100)  # the work email they sign in to MAEC One with
    job_role: str = Field(max_length=150)


class PersonUpdate(BaseModel):
    """Only the fields given change. Not the email: that is who the person is in MAEC One."""

    full_name: str | None = Field(default=None, max_length=150)
    job_role: str | None = Field(default=None, max_length=150)


@router.post("/import")
async def import_people(
    file: UploadFile = File(...),
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Create a profile (employee record and engineer user, no password) for everyone in the CSV
    who doesn't have one. Each still needs a seat on Project Management in MAEC One."""
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise BadRequestError("The file is too large for an employee list.")
    return service.import_people(read_people(content))


@router.post("", status_code=201)
def add_person(
    payload: PersonIn,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """One profile, for someone given a seat in MAEC One who has none here yet."""
    return service.add_person(payload.employee_code, payload.full_name, payload.email, payload.job_role)


@router.get("")
def list_people(
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Everyone with a profile, with what the BU Head may do to each."""
    return service.list_people()


@router.patch("/{user_id}")
def update_person(
    user_id: int,
    payload: PersonUpdate,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    return service.update_person(user_id, payload.full_name, payload.job_role)


@router.post("/{user_id}/make-bu-head")
def make_bu_head(
    user_id: int,
    payload: RoleChangeIn,
    user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Only an engineer on no live project; 409 names the projects otherwise."""
    return service.make_bu_head(user, user_id, payload.confirm)


@router.post("/{user_id}/remove-bu-head")
def remove_bu_head(
    user_id: int,
    payload: RoleChangeIn,
    user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Back to engineer: never the last BU Head, never yourself."""
    return service.remove_bu_head(user, user_id, payload.confirm)
