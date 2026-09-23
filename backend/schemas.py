from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

PROJECT_TYPES = {
    "MEP Design",
    "Structural Design",
    "Architectural Design",
    "BIM Coordination",
    "Construction Management",
    "Other",
}

WBS_PHASES = ("Space Planning", "STR Coordination", "ID Coordination", "BoH Area RCP Coordination", "Submission")

WBS_TASK_STATUSES = ["To Do", "In-Progress", "Submitted for Approval", "Approved"]
WBS_SUBTASK_STATUSES = ["To Do", "In-Progress", "Done"]

WBS_STATUS_FLOWS = {
    "task": WBS_TASK_STATUSES,
    "subtask": WBS_SUBTASK_STATUSES,
}


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    id: int
    role: str
    username: str
    full_name: Optional[str] = None
    engineer_id: Optional[int] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    employee_id: Optional[int] = None
    discipline: Optional[str] = None


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
    contract_value: Optional[float] = 0
    contract_currency: str = "USD"
    governance_threshold_pct: Optional[float] = 80


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
    sharepoint_disciplines: Optional[str] = None
    target_effort_hours: Optional[float] = None
    sharepoint_site_url: Optional[str] = None


class ProjectCreatePayload(BaseModel):
    """JSON body POSTed by the BU Head 'Create Project' form on /api/projects.

    The frontend form fields map directly onto the existing projects table
    (plus the ALTER-migrated governance/lead columns) so creation and the
    'Created Projects' list share one model.
    """
    project_name: str
    project_code: str
    client_customer: str
    project_lead_electrical: str
    project_lead_mechanical: str
    project_lead_bim: str
    project_lead_electrical_user_id: Optional[int] = None
    project_lead_mechanical_user_id: Optional[int] = None
    project_lead_bim_user_id: Optional[int] = None
    target_start_date: Optional[date] = None
    sharepoint_disciplines: Optional[List[str]] = None
    total_contract_value: float = 0
    contract_currency: str = "USD"
    target_effort_hours: float = 0
    alert_override_threshold_pct: float = 80

    @field_validator("project_name", "project_code", "client_customer", "project_lead_electrical", "project_lead_mechanical", "project_lead_bim")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("This field cannot be blank")
        return v.strip()

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


class WbsTaskUpdate(BaseModel):
    task_name: str
    wbs_code: str
    status: str
    planned_hours: int = 0
    assigned_engineer_id: Optional[int] = None


class WbsTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    wbs_code: str
    task_name: str
    status: str
    planned_hours: int
    assigned_engineer_id: Optional[int] = None
    assigned_engineer_name: Optional[str] = None


class WbsNodeBase(BaseModel):
    wbs_code: Optional[str] = None
    task_name: str
    parent_id: Optional[int] = None
    assigned_lead: Optional[str] = None
    assigned_lead_user_id: Optional[int] = None
    assigned_engineer_id: Optional[int] = None
    estimated_hours: Optional[int] = None
    deliverable_status: str = "Not Started"
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
        phase = str(value).strip()
        if phase not in WBS_PHASES:
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
    level: int = 1


class WbsNodeUpdate(WbsNodeBase):
    pass


class TimeLogEntryCreate(BaseModel):
    task_id: int
    week_start_date: date
    mon_hours: float = 0
    tue_hours: float = 0
    wed_hours: float = 0
    thu_hours: float = 0
    fri_hours: float = 0
    sat_hours: float = 0
    sun_hours: float = 0

    @field_validator("mon_hours", "tue_hours", "wed_hours", "thu_hours", "fri_hours", "sat_hours", "sun_hours")
    @classmethod
    def hours_in_range(cls, value: float) -> float:
        value = float(value or 0)
        if value < 0 or value > 24:
            raise ValueError("Daily hours must be between 0 and 24.")
        return value


class TimeLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    task_id: int
    wbs_code: Optional[str] = None
    task_name: Optional[str] = None
    employee_id: int
    employee_name: Optional[str] = None
    week_start_date: date
    mon_hours: float
    tue_hours: float
    wed_hours: float
    thu_hours: float
    fri_hours: float
    sat_hours: float
    sun_hours: float
    total_hours: float
    approval_status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class SubtaskTrackingStart(BaseModel):
    subtask_id: int


class SubtaskSessionSync(BaseModel):
    active_seconds: int

    @field_validator("active_seconds")
    @classmethod
    def non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("active_seconds cannot be negative.")
        return value


class SubtaskSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    task_id: int
    subtask_id: int
    employee_id: int
    login_at: datetime
    logout_at: Optional[datetime] = None
    active_seconds: int
    status: str


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

