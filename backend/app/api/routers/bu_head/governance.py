from fastapi import APIRouter, Depends

import models
import schemas
from app.api.deps import get_governance_service, get_work_summary_service
from app.core.security import require_bu_head, require_lead_or_bu_head
from app.services.governance import GovernanceService
from app.services.work_summary import WorkSummaryService

router = APIRouter(prefix="/projects/{project_id}", tags=["governance"])


@router.get("/executive-dashboard")
def executive_dashboard(
    project_id: int,
    user: models.User = Depends(require_lead_or_bu_head),
    service: GovernanceService = Depends(get_governance_service),
):
    """Budget burn, hours consumption, threshold status, SPI, monthly chart,
    extension requests and the governance audit log."""
    return service.executive_dashboard(user, project_id)


@router.post("/extension-requests/{request_id}/decision", response_model=schemas.ExtensionRequestOut)
def decide_extension_request(
    project_id: int,
    request_id: int,
    payload: schemas.ExtensionRequestDecision,
    user: models.User = Depends(require_bu_head),
    service: GovernanceService = Depends(get_governance_service),
):
    return service.decide_extension(user, project_id, request_id, payload.decision, payload.comments)


@router.post("/governance/stop-execution", response_model=schemas.GovernanceActionOut)
def stop_execution(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(require_bu_head),
    service: GovernanceService = Depends(get_governance_service),
):
    """Soft-lock timesheets: engineers cannot log hours and leads cannot approve them."""
    return service.stop_execution(user, project_id, payload)


@router.get("/work-summary")
def work_summary(
    project_id: int,
    _user: models.User = Depends(require_bu_head),
    service: WorkSummaryService = Depends(get_work_summary_service),
):
    """Per-lead oversight and per-engineer contribution for one project."""
    return service.summary(project_id)
