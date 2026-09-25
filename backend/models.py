from sqlalchemy import Boolean, Column, Integer, String, Date, DateTime, Text, Float, UniqueConstraint, true
from sqlalchemy.orm import validates
from sqlalchemy.sql import func

from app.domain.wbs import TO_DO, normalize_status
from database import Base


class Project(Base):
    """
    A single project proposal, as created by a BU Admin on the
    'Create New Project' screen.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    project_name = Column(String(200), nullable=False)
    project_code = Column(String(50), nullable=False, unique=True, index=True)
    client_organization = Column(String(200), nullable=False)
    project_lead = Column(String(150), nullable=False)

    # BU Head 'Create Project' form fields. These are columns on the existing
    # projects table (added via ALTER migration) — no separate model/table.
    project_lead_electrical = Column(String(150), nullable=True)
    project_lead_mechanical = Column(String(150), nullable=True)
    project_lead_bim = Column(String(150), nullable=True)
    # Real Lead user IDs (users.id) backing the display-name columns above, so
    # access-scoping uses real user ID matching instead of name strings.
    project_lead_electrical_user_id = Column(Integer, nullable=True)
    project_lead_mechanical_user_id = Column(Integer, nullable=True)
    project_lead_bim_user_id = Column(Integer, nullable=True)
    sharepoint_disciplines = Column(Text, nullable=True)
    target_effort_hours = Column(Float, nullable=True, default=None)

    start_date = Column(Date, nullable=True)
    target_end_date = Column(Date, nullable=True)
    project_type = Column(String(100), nullable=True)

    scope_description = Column(Text, nullable=True)

    # Stored filename of the uploaded proposal/SOW document, if any.
    proposal_attachment = Column(String(255), nullable=True)

    # Governance / executive-dashboard metadata.
    contract_value = Column(Float, nullable=False, default=0)
    contract_currency = Column(String(10), nullable=False, default="USD")
    governance_threshold_pct = Column(Float, nullable=False, default=80)
    timesheets_soft_locked = Column(Boolean, nullable=False, default=False)
    # Governance state (app/domain/governance.py): why timesheets are locked
    # ('manual' | 'auto') and the last alert level notified, so each level is
    # announced once when crossed rather than on every logged hour.
    lock_reason = Column(String(20), nullable=True)
    governance_alert_level = Column(String(20), nullable=True)
    extension_status = Column(String(20), nullable=True, index=True)
    extension_approved_hours = Column(Float, nullable=True)
    sharepoint_site_url = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProjectLead(Base):
    """
    Simple lookup table backing the 'Project Lead' dropdown.
    In a real system this would likely come from an Employees/Users table.
    """
    __tablename__ = "project_leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, unique=True)
    title = Column(String(150), nullable=True)


class User(Base):
    """
    An account that can log in to MAEC. Role gates every API endpoint —
    role is never read from a URL parameter or client header.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=True)
    role = Column(String(20), nullable=False, index=True)  # bu_head | lead | engineer
    # Discipline attribute for Lead accounts (Electrical / Mechanical / BIM),
    # used to filter the real Lead accounts for project-lead assignment.
    discipline = Column(String(100), nullable=True)
    # For leads/engineers this links the account to an employee row so
    # data scoping (assigned_lead, assigned_engineer_id) resolves server-side.
    employee_id = Column(Integer, nullable=True, index=True)
    # Deactivated accounts (leavers) can't log in and their sessions stop working.
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LoginSession(Base):
    """
    A bearer token row created on successful login and deleted on logout.
    The token identifies the logged-in user on every subsequent request.
    """
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(50), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    role_title = Column(String(150), nullable=False)
    discipline = Column(String(100), nullable=True)


class GanttTask(Base):
    __tablename__ = "gantt_tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    wbs_code = Column(String(50), nullable=False)
    task_name = Column(String(200), nullable=False)
    status = Column(String(40), nullable=False, default="scheduled")
    planned_hours = Column(Integer, nullable=False, default=0)
    assigned_engineer_id = Column(Integer, nullable=True, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ResourceBooking(Base):
    __tablename__ = "resource_bookings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    planned_hours = Column(Integer, nullable=False, default=0)
    utilization_rate = Column(Integer, nullable=False, default=0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # BU Head approval workflow state. draft -> pending_approval -> approved.
    approval_status = Column(String(20), nullable=False, default="draft", index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    """A persisted, role-targeted notification (e.g. BU Head approval queue)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_role = Column(String(20), nullable=False, index=True)  # bu_head | lead | engineer
    recipient_user_id = Column(Integer, nullable=True, index=True)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    project_id = Column(Integer, nullable=True, index=True)
    actor_name = Column(String(150), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WbsNode(Base):
    __tablename__ = "wbs_nodes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, nullable=True, index=True)
    wbs_code = Column(String(80), nullable=True, index=True)
    task_name = Column(String(240), nullable=False)
    assigned_lead = Column(String(150), nullable=True)
    assigned_lead_user_id = Column(Integer, nullable=True)
    assigned_engineer_id = Column(Integer, nullable=True, index=True)
    estimated_hours = Column(Integer, nullable=True, default=None)
    deliverable_status = Column(String(40), nullable=False, default=TO_DO)
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=True)
    start_date = Column(Date, nullable=True)
    target_due_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    actual_start_datetime = Column(DateTime(timezone=True), nullable=True)
    actual_end_datetime = Column(DateTime(timezone=True), nullable=True)
    phase = Column(String(50), nullable=True, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @validates("deliverable_status")
    def _canonical_status(self, _key, status):
        # Every write stores a canonical status (app/domain/wbs.py), whatever the
        # source (form, edit, Excel upload). parent_id is set before the status on
        # every write path, so the legacy "Completed" maps to Done/Approved correctly.
        return normalize_status(status, is_subtask=self.parent_id is not None)


class WbsNodeHistory(Base):
    __tablename__ = "wbs_node_history"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_name = Column(String(150), nullable=False)
    action = Column(String(40), nullable=False)
    old_status = Column(String(40), nullable=True)
    new_status = Column(String(40), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GovernanceAction(Base):
    """
    An audited BU Head governance decision against a project.

    Every entry is persisted so the executive dashboard can show the
    'Recent Governance Audit Log' with real rows, most recent first.
    """
    __tablename__ = "governance_actions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    action = Column(String(40), nullable=False)  # stop_execution | reject_extension
    discipline = Column(String(100), nullable=True)
    consumption_pct = Column(Float, nullable=True)
    threshold_pct = Column(Float, nullable=True)
    consumption_hours = Column(Float, nullable=True)
    comments = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=True)
    extension_request_id = Column(Integer, nullable=True, index=True)
    requested_hours = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExtensionRequest(Base):
    """
    A persisted request from a Lead for additional governance hours.

    The request row is the source of truth for BU Head review and Lead status.
    GovernanceAction rows remain the audit trail for each workflow event.
    """
    __tablename__ = "extension_requests"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    requested_by = Column(String(150), nullable=False, index=True)
    requested_by_user_id = Column(Integer, nullable=False, index=True)
    requested_hours = Column(Float, nullable=False)
    justification = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    decision_comments = Column(Text, nullable=True)
    decided_by = Column(String(150), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)


DAY_FIELDS = ("mon_hours", "tue_hours", "wed_hours", "thu_hours", "fri_hours", "sat_hours", "sun_hours")


class TimeLogEntry(Base):
    """
    Weekly submitted working-hours log against a real WBS node assignment.

    One row per (project, WBS task, engineer, ISO week). Scoped server-side by
    role: an engineer only ever sees/edits their own rows; a lead sees rows for
    tasks assigned under them and may approve/reject them; BU Head sees the
    project-wide rollup.
    """
    __tablename__ = "time_log_entries"
    __table_args__ = (
        UniqueConstraint("project_id", "task_id", "employee_id", "week_start_date", name="uq_time_log_week"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    mon_hours = Column(Float, nullable=False, default=0)
    tue_hours = Column(Float, nullable=False, default=0)
    wed_hours = Column(Float, nullable=False, default=0)
    thu_hours = Column(Float, nullable=False, default=0)
    fri_hours = Column(Float, nullable=False, default=0)
    sat_hours = Column(Float, nullable=False, default=0)
    sun_hours = Column(Float, nullable=False, default=0)
    approval_status = Column(String(20), nullable=False, default="pending_review")
    reviewed_by = Column(String(150), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class WeeklyHoursSubmission(Base):
    """
    An engineer's weekly-hours submission for one project + ISO week.

    Unlike TimeLogEntry (one row per task/subtask), this is the WEEK-level
    workflow record the Weekly Hours section keys off of. A row only exists
    once the engineer submits: status goes not_submitted -> submitted ->
    approved | rejected. Only a week whose status is exactly 'submitted' can
    be approved or rejected — enforced server-side, never just in the UI.
    """
    __tablename__ = "weekly_hours_submissions"
    __table_args__ = (
        UniqueConstraint("project_id", "employee_id", "week_start_date", name="uq_weekly_hours_submission"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    week_start_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="submitted", index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(150), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TimeSession(Base):
    """
    An automatic working-time tracking session for a single subtask.

    Engineers start/stop a session while actively working on an assigned
    subtask. Only ACTIVE interaction is counted — idle/background time is
    excluded by the client, which reports the cumulative active seconds on a
    heartbeat; the backend persists them and caps the per-engineer daily
    total at 8 hours. One row per tracking session.
    """
    __tablename__ = "time_sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    subtask_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    login_at = Column(DateTime(timezone=True), nullable=False, index=True)
    logout_at = Column(DateTime(timezone=True), nullable=True)
    active_seconds = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
