"""BU Head endpoints: projects & SharePoint, governance, resourcing approval, project estimation."""

from fastapi import APIRouter

from app.api.routers.bu_head import estimations, governance, people, projects, resourcing

router = APIRouter()
router.include_router(projects.router)
router.include_router(governance.router)
router.include_router(resourcing.router)
router.include_router(people.router)
router.include_router(estimations.router)
