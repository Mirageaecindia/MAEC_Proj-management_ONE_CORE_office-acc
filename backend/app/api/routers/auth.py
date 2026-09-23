import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from app.core.database import get_db
from app.core.roles import Role
from app.core.security import bearer_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = secrets.token_hex(32)
    db.add(models.LoginSession(token=token, user_id=user.id))
    db.commit()
    return schemas.LoginResponse(
        token=token,
        id=user.id,
        role=user.role,
        username=user.username,
        full_name=user.full_name,
        engineer_id=user.employee_id if user.role == Role.ENGINEER else None,
    )


@router.post("/logout")
def logout(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """Idempotent: logging out with a missing or already-deleted token succeeds."""
    token = bearer_token(authorization)
    if token:
        db.query(models.LoginSession).filter_by(token=token).delete()
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
