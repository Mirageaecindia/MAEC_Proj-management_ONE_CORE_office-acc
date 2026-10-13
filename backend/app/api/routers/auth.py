"""/api/auth/me: who the signed-in person is in this app.

There is no sign-in, sign-out or password change here: all three happen at MAEC One Core.
By the time a request reaches this route the gate (app/api/gate.py) has asked Core, and
app/core/identity.py has found the person's users row.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
import schemas
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_session_user
from app.services.access import leads_any_project

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_session_user), db: Session = Depends(get_db)):
    return {
        **schemas.UserOut.model_validate(user).model_dump(),
        "leads_projects": leads_any_project(db, user),
        # Where "Sign out" and "Change password" go: MAEC One, as a browser reaches it.
        "core_url": get_settings().core_public_url,
    }
