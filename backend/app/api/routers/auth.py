from fastapi import APIRouter, Depends, Header

import models
import schemas
from app.api.deps import get_auth_service
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import bearer_token, get_session_user
from app.services.access import leads_any_project
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, service: AuthService = Depends(get_auth_service)):
    """Returns a bearer token. Repeated failures lock the username temporarily (429)."""
    return service.login(payload.username, payload.password)


@router.post("/logout")
def logout(authorization: str | None = Header(None), service: AuthService = Depends(get_auth_service)):
    service.logout(bearer_token(authorization))
    return {"ok": True}


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_session_user), db: Session = Depends(get_db)):
    return {**schemas.UserOut.model_validate(user).model_dump(), "leads_projects": leads_any_project(db, user)}


@router.post("/change-password")
def change_password(
    payload: schemas.ChangePasswordIn,
    authorization: str | None = Header(None),
    user: models.User = Depends(get_session_user),  # also while a temporary password is still in use
    service: AuthService = Depends(get_auth_service),
):
    """The person replaces their password (a temporary one, or any time). Their other sessions end."""
    service.change_password(user, bearer_token(authorization), payload.current_password, payload.new_password)
    return {"ok": True}
