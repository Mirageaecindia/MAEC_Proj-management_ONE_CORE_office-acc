"""People (BU Head): import engineers from an HR export, list, correct, deactivate, reset a password.

Temporary, until the company's global admin application owns people and access
(decided 2026-10-03). The rules are in app/services/provisioning.py, which that
application will call instead.
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


class ResetPasswordIn(BaseModel):
    username: str


class PersonUpdate(BaseModel):
    """Only the fields given change."""

    full_name: str | None = Field(default=None, max_length=150)
    username: str | None = Field(default=None, max_length=100)  # the work email they sign in with
    job_role: str | None = Field(default=None, max_length=150)


@router.post("/import")
async def import_people(
    file: UploadFile = File(...),
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Create an engineer account for everyone in the CSV who doesn't have one. The response
    carries each new account's temporary password: the only time it can be read."""
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise BadRequestError("The file is too large for an employee list.")
    return service.import_people(read_people(content))


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    return service.reset_password(payload.username)


@router.get("")
def list_people(
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Everyone with an account, with what the BU Head may do to each. Never passwords."""
    return service.list_people()


@router.patch("/{user_id}")
def update_person(
    user_id: int,
    payload: PersonUpdate,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    return service.update_person(user_id, payload.full_name, payload.username, payload.job_role)


@router.post("/{user_id}/deactivate")
def deactivate_person(
    user_id: int,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    return service.set_active(user_id, False)


@router.post("/{user_id}/reactivate")
def reactivate_person(
    user_id: int,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    return service.set_active(user_id, True)


@router.delete("/{user_id}")
def delete_person(
    user_id: int,
    _user: models.User = Depends(require_bu_head),
    service: Provisioning = Depends(get_provisioning),
):
    """Only an account with no work on record; otherwise 409, deactivate instead."""
    service.delete_person(user_id)
    return {"ok": True}
