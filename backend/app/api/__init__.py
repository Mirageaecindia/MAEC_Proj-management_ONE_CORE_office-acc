"""HTTP layer: every router in the app package, mounted under /api by main.py."""

from fastapi import APIRouter

from app.api.routers import audit, auth, bu_head, engineer, rejected_hours, team_members, wbs_blueprints

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(bu_head.router)
api_router.include_router(engineer.router)
api_router.include_router(rejected_hours.router)
api_router.include_router(team_members.router)
api_router.include_router(audit.router)
api_router.include_router(wbs_blueprints.router)
