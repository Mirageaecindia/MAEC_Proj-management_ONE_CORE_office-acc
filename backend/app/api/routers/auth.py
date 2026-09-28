from fastapi import APIRouter, Depends, Header

import models
import schemas
from app.api.deps import get_auth_service
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import bearer_token, get_current_user
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
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {**schemas.UserOut.model_validate(user).model_dump(), "leads_projects": leads_any_project(db, user)}
