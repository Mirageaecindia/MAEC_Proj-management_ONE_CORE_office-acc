from datetime import date, datetime
from typing import Literal, List, Optional

from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator

from app.domain.wbs import PHASES, current_phase

PROJECT_TYPES = {
    "MEP Design",
    "Structural Design",
    "Architectural Design",
    "BIM Coordination",
    "Construction Management",
    "Other",
}

WBS_PHASES = PHASES

WBS_TASK_STATUSES = ["To Do", "In-Progress", "Submitted for Approval", "Approved"]
WBS_SUBTASK_STATUSES = ["To Do", "In-Progress", "Done"]

WBS_STATUS_FLOWS = {
    "task": WBS_TASK_STATUSES,
    "subtask": WBS_SUBTASK_STATUSES,
}


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    employee_id: Optional[int] = None
    leads_projects: bool = False
    core_url: str = ""  # MAEC One as a browser reaches it: "Sign out" and "Change password" link there


class EngineerPerformanceOut(BaseModel):
    summary: dict
    projects: list
    recent_entries: list = []


class EngineerDashboardProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_name: str
    project_code: str
    client_organization: str
    project_lead: str
    contract_value: Optional[float] = None
    contract_currency: Optional[str] = None
    governance_threshold_pct: Optional[float] = None


class EngineerDashboardMonthlyOut(BaseModel):
    month: str
    month_label: str
    planned_baseline: float
    normal_consumption: float
    exceeded_threshold: float


class EngineerDashboardSummaryOut(BaseModel):
    total_hours_consumption: float
    total_hours_scheduled: float
    total_hours_approved: float
    total_hours_pending: float
    consumption_pct: float
    governance_consumption_pct: float
    governance_status: str
    governance_threshold_pct: Optional[float]
    governance_exceeded: bool
    spi_value: Optional[float]
    spi_note: str
    total_tasks: int
    started_tasks: int
    completed_tasks: int
    completion_pct: int
    schedule_status: Optional[str] = None


class EngineerDashboardOut(BaseModel):
    summary: EngineerDashboardSummaryOut
    projects: List[EngineerDashboardProjectOut]
    monthly_breakdown: List[EngineerDashboardMonthlyOut]


class ProjectBase(BaseModel):
    project_name: str
    project_code: str
    client_organization: str
    project_lead: str
    start_date: Optional[date] = None
    target_end_date: Optional[date] = None
    project_type: Optional[str] = None
    scope_description: Optional[str] = None

    @field_validator("project_name", "project_code", "client_organization", "project_lead")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field cannot be blank")
        return v.strip()

    @field_validator("target_end_date")
    @classmethod
    def end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if v and start and v < start:
            raise ValueError("Target End Date cannot be before Start Date")
        return v


class ProjectCreate(ProjectBase):
    pass


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proposal_attachment: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Governance/commercial + BU Head 'Create Project' form metadata.
    contract_value: Optional[float] = 0
    contract_currency: Optional[str] = "USD"
    governance_threshold_pct: Optional[float] = 80
    timesheets_soft_locked: Optional[bool] = False
    extension_status: Optional[str] = None
    extension_approved_hours: Optional[float] = None
    project_lead_electrical: Optional[str] = None
    project_lead_mechanical: Optional[str] = None
    project_lead_bim: Optional[str] = None
    project_lead_electrical_user_id: Optional[int] = None
    project_lead_mechanical_user_id: Optional[int] = None
    project_lead_bim_user_id: Optional[int] = None
    # Filled from the lead bookings by ProjectService (None for a name-only legacy lead).
    project_lead_electrical_start_date: Optional[date] = None
    project_lead_electrical_end_date: Optional[date] = None
    project_lead_electrical_utilization_pct: Optional[int] = None
    project_lead_mechanical_start_date: Optional[date] = None
    project_lead_mechanical_end_date: Optional[date] = None
    project_lead_mechanical_utilization_pct: Optional[int] = None
    project_lead_bim_start_date: Optional[date] = None
    project_lead_bim_end_date: Optional[date] = None
    project_lead_bim_utilization_pct: Optional[int] = None
    sharepoint_disciplines: Optional[str] = None
    target_effort_hours: Optional[float] = None
    sharepoint_site_url: Optional[str] = None
    archived_at: Optional[datetime] = None
    my_role: Optional[str] = None  # the caller's role on this project: bu_head | lead | engineer


LEAD_SLOTS = ("electrical", "mechanical", "bim")


class LeadAssignment(BaseModel):
    """One project lead slot as the BU Head filled it in."""

    slot: str
    name: Optional[str] = None
    user_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    utilization_pct: Optional[int] = None


class ProjectFields(BaseModel):
    """Project fields the BU Head sets on the Create Project form and can later edit."""
    project_name: str
    project_code: str
    client_customer: str
    # Each discipline's lead is optional (a project may not need all three); at least one is required.
    project_lead_electrical: Optional[str] = None
    project_lead_mechanical: Optional[str] = None
    project_lead_bim: Optional[str] = None
    project_lead_electrical_user_id: Optional[int] = None
    project_lead_mechanical_user_id: Optional[int] = None
    project_lead_bim_user_id: Optional[int] = None
    # A lead holds part of their capacity on the project for a period (see LeadAssignment).
    project_lead_electrical_start_date: Optional[date] = None
    project_lead_electrical_end_date: Optional[date] = None
    project_lead_electrical_utilization_pct: Optional[int] = None
    project_lead_mechanical_start_date: Optional[date] = None
    project_lead_mechanical_end_date: Optional[date] = None
    project_lead_mechanical_utilization_pct: Optional[int] = None
    project_lead_bim_start_date: Optional[date] = None
    project_lead_bim_end_date: Optional[date] = None
    project_lead_bim_utilization_pct: Optional[int] = None
    target_start_date: Optional[date] = None
    total_contract_value: float = 0
    contract_currency: str = "USD"
    target_effort_hours: float = 0
    alert_override_threshold_pct: float = 80

    @field_validator("project_name", "project_code", "client_customer")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field cannot be blank")
        return v.strip()

    @field_validator("project_lead_electrical", "project_lead_mechanical", "project_lead_bim")
    @classmethod
    def blank_lead_is_none(cls, v: Optional[str]) -> Optional[str]:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def at_least_one_lead(self):
        leads = (
            self.project_lead_electrical, self.project_lead_electrical_user_id,
            self.project_lead_mechanical, self.project_lead_mechanical_user_id,
            self.project_lead_bim, self.project_lead_bim_user_id,
        )  # fmt: skip
        if not any(leads):
            raise ValueError("Choose at least one project lead")
        for slot in LEAD_SLOTS:
            self._check_assignment(slot)
        return self

    def _check_assignment(self, slot: str) -> None:
        """A lead chosen by account needs a start date, an end date and a utilization %."""
        assignment = self.lead_assignment(slot)
        if assignment.user_id is None:
            return
        if assignment.start_date is None or assignment.end_date is None or assignment.utilization_pct is None:
            raise ValueError(f"Give the {slot} lead a start date, an end date and a utilization %")
        if assignment.end_date < assignment.start_date:
            raise ValueError(f"The {slot} lead's end date is before their start date")
        if not 1 <= assignment.utilization_pct <= 100:
            raise ValueError(f"The {slot} lead's utilization must be between 1 and 100%")

    def lead_assignment(self, slot: str) -> "LeadAssignment":
        prefix = f"project_lead_{slot}"
        return LeadAssignment(
            slot=slot,
            name=getattr(self, prefix),
            user_id=getattr(self, f"{prefix}_user_id"),
            start_date=getattr(self, f"{prefix}_start_date"),
            end_date=getattr(self, f"{prefix}_end_date"),
            utilization_pct=getattr(self, f"{prefix}_utilization_pct"),
        )

    @field_validator("alert_override_threshold_pct")
    @classmethod
    def threshold_in_range(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("Alert and Override Threshold must be between 0 and 100")
        return v

    @field_validator("total_contract_value", "target_effort_hours")
    @classmethod
    def non_negative(cls, v: float) -> float:
        return max(0.0, float(v or 0))


class ProjectCreatePayload(ProjectFields):
    """JSON body POSTed by the BU Head 'Create Project' form on /api/projects."""
    sharepoint_disciplines: Optional[List[str]] = None


class ProjectUpdatePayload(ProjectFields):
    """JSON body PUT to /api/projects/{id}. SharePoint folders are not re-provisioned on edit.
    Changing the currency relabels amounts without converting them, so it must be confirmed."""
    confirm_currency_change: bool = False


class ProjectUpdateOut(ProjectOut):
    reassigned_nodes: int = 0


class CreateProjectOut(ProjectOut):
    sharepoint_status: Optional[str] = None
    sharepoint_site_url: Optional[str] = None
    sharepoint_error: Optional[str] = None


class ProjectLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: Optional[str] = None


class EngineerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    name: str
    role_title: str
    discipline: Optional[str] = None
    user_id: Optional[int] = None


class WbsNodeBase(BaseModel):
    wbs_code: Optional[str] = None
    task_name: str
    parent_id: Optional[int] = None
    assigned_lead: Optional[str] = None
    assigned_lead_user_id: Optional[int] = None
    assigned_engineer_id: Optional[int] = None
    estimated_hours: Optional[int] = None
    deliverable_status: str = "To Do"
    start_date: Optional[date] = None
    target_due_date: Optional[date] = None
    end_date: Optional[date] = None
    subtask: Optional[str] = None
    phase: Optional[str] = None

    @field_validator("phase")
    @classmethod
    def phase_is_fixed(cls, value):
        if value is None or not str(value).strip():
            return None
        phase = current_phase(value)  # an old phase name is taken under its new one
        if phase is None:
            raise ValueError("Phase must be one of the five fixed phases.")
        return phase

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, value, info):
        start = info.data.get("start_date")
        if value and start and value < start:
            raise ValueError("End Date cannot be before Start Date")
        return value


class WbsNodeOut(WbsNodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    assigned_engineer_name: Optional[str] = None
    created_by_user_id: Optional[int] = None  # an engineer deletes only subtasks they created
    level: int = 1


class WbsNodeUpdate(WbsNodeBase):
    pass


class WbsNodesDeleteIn(BaseModel):
    """Tasks and subtasks selected for deletion; all of them or none."""

    node_ids: list[int] = Field(min_length=1)


class ResourceBookingIn(BaseModel):
    """A Lead's booking of an engineer on a project (dates optional: the WBS dates fill in)."""

    employee_id: int
    utilization_rate: int = Field(default=0, ge=0, le=100)
    planned_hours: int = Field(default=0, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date is before the start date")
        return self


class ResourceBookingUpdate(BaseModel):
    """Fields a Lead may change on a booking; anything omitted stays as it is."""

    employee_id: Optional[int] = None
    utilization_rate: Optional[int] = Field(default=None, ge=0, le=100)
    planned_hours: Optional[int] = Field(default=None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class HoursReviewIn(BaseModel):
    """Bulk review: every pending, finished day in the week that the caller is responsible for."""

    action: Literal["approved", "rejected"]
    week_start_date: date
    employee_id: Optional[int] = None  # one engineer, or everyone on the caller's tasks
    reason: Optional[str] = None  # required when rejecting


class HoursDecisionIn(BaseModel):
    """One day's hours. A reason is required to reject hours that were already approved."""

    reason: Optional[str] = None


class GovernanceActionBase(BaseModel):
    comments: str
    discipline: Optional[str] = None

    @field_validator("comments")
    @classmethod
    def comments_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("A BU Head Approval Comment / Justification is required.")
        return v


class GovernanceDecisionBase(BaseModel):
    request_id: Optional[int] = None
    comments: str

    @field_validator("comments")
    @classmethod
    def comments_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("A BU Head decision comment is required.")
        return v


class GovernanceActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    action: str
    discipline: Optional[str] = None
    consumption_pct: Optional[float] = None
    threshold_pct: Optional[float] = None
    consumption_hours: Optional[float] = None
    comments: Optional[str] = None
    created_by: Optional[str] = None
    extension_request_id: Optional[int] = None
    requested_hours: Optional[float] = None
    created_at: datetime


class ExtensionRequestCreate(BaseModel):
    requested_hours: float
    justification: Optional[str] = None

    @field_validator("requested_hours")
    @classmethod
    def requested_hours_positive(cls, value: float) -> float:
        value = float(value or 0)
        if value <= 0:
            raise ValueError("Requested additional hours must be greater than zero.")
        return value

    @field_validator("justification")
    @classmethod
    def justification_is_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LegacyExtensionRequestCreate(BaseModel):
    comments: str

    @field_validator("comments")
    @classmethod
    def comments_are_text(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("A request comment is required.")
        return value


class ExtensionRequestDecision(BaseModel):
    decision: str
    comments: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def decision_is_supported(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in {"approve", "reject"}:
            raise ValueError("Decision must be approve or reject.")
        return value

    @field_validator("comments")
    @classmethod
    def comments_are_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ExtensionRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    project_name: str
    requested_by: str
    requested_by_user_id: int
    requested_hours: float
    justification: Optional[str] = None
    status: str
    status_label: str
    decision_comments: Optional[str] = None
    decided_by: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None


class WbsNodeDetailOut(WbsNodeOut):
    model_config = ConfigDict(from_attributes=True)

    description: Optional[str] = None
    severity: Optional[str] = None
    actual_start_datetime: Optional[str] = None
    actual_end_datetime: Optional[str] = None
    node_type: str = "task"
    reference_only: bool = False  # a sub-subtask: no Login/Logout, no hours
    linked_code: Optional[str] = None
    linked_task_name: Optional[str] = None
    history: List["WbsNodeHistoryOut"] = []
    children: List[dict] = []


class WbsNodeHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    user_name: str
    action: str
    old_status: Optional[str] = None
    new_status: str
    comment: Optional[str] = None
    created_at: datetime


class WbsNodeStatusUpdate(BaseModel):
    new_status: str
    comment: Optional[str] = None


class WbsNodeCommentInput(BaseModel):
    comment: str

    @field_validator("comment")
    @classmethod
    def comment_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Comment text is required.")
        return v


class WbsNodeCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    user_name: str
    action: str
    old_status: Optional[str] = None
    new_status: str
    comment: Optional[str] = None
    created_at: datetime

