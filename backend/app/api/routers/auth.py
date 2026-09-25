from fastapi import APIRouter, Depends, Header

import models
import schemas
from app.api.deps import get_auth_service
from app.core.security import bearer_token, get_current_user
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
def me(user: models.User = Depends(get_current_user)):
    return user
