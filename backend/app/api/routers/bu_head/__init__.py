"""BU Head endpoints: projects & SharePoint, governance, resourcing approval."""

from fastapi import APIRouter

from app.api.routers.bu_head import governance, projects, resourcing

router = APIRouter()
router.include_router(projects.router)
router.include_router(governance.router)
router.include_router(resourcing.router)
