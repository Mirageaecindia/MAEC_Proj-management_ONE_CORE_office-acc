"""HTTP layer: every router in the app package, mounted under /api by main.py."""

from fastapi import APIRouter

from app.api.routers import auth, bu_head

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(bu_head.router)
