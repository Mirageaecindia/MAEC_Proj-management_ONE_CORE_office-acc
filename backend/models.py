from datetime import UTC

from sqlalchemy import Boolean, Column, Integer, String, Date, DateTime, Text, Float, UniqueConstraint, true
from sqlalchemy.orm import validates
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from app.domain.wbs import TO_DO, normalize_status
from database import Base



class UTCDateTime(TypeDecorator):
    """A timestamp that is always UTC, and says so.

    Every timestamp in this app is stored in UTC. SQLite hands them back without
    a time zone, and a value serialised that way ("2026-09-30T04:00:00") is read
    by a browser as local time. This type attaches UTC on the way out of the
    database (and on the way in, for a naive value), so every API response
    carries an explicit offset and the browser can show local time correctly.
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


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
    # Set when the BU Head archives the project; archived projects are read-only (app/services/archive_guard.py).
    archived_at = Column(UTCDateTime, nullable=True, index=True)
    sharepoint_site_url = Column(String(500), nullable=True)

    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, onupdate=func.now())


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
    # bu_head | engineer. "Lead" is a role on a project (app/services/access.py), not an account type.
    role = Column(String(20), nullable=False, index=True)
    # Set for a temporary password (onboarding, reset): nothing works until the person sets their own.
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")
    # Engineers are linked to an employee row so data scoping (bookings,
    # assigned_engineer_id, hours) resolves server-side.
    employee_id = Column(Integer, nullable=True, index=True)
    # Deactivated accounts (leavers) can't log in and their sessions stop working.
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    created_at = Column(UTCDateTime, server_default=func.now())


class LoginSession(Base):
    """
    A bearer token row created on successful login and deleted on logout.
    The token identifies the logged-in user on every subsequent request.
    """
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(UTCDateTime, server_default=func.now())


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
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class ResourceBooking(Base):
    __tablename__ = "resource_bookings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    # "engineer": booked by a lead of the project, approved by the BU Head.
    # "lead": the BU Head's own assignment of a project lead (Create/Edit
    # Project), approved from the start. Both hold the person's capacity.
    role = Column(String(20), nullable=False, default="engineer", server_default="engineer", index=True)
    planned_hours = Column(Integer, nullable=False, default=0)
    utilization_rate = Column(Integer, nullable=False, default=0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # BU Head approval workflow state. draft -> pending_approval -> approved.
    approval_status = Column(String(20), nullable=False, default="draft", index=True)
    submitted_at = Column(UTCDateTime, nullable=True)
    approved_at = Column(UTCDateTime, nullable=True)


class Notification(Base):
    """A persisted, role-targeted notification (e.g. BU Head approval queue)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_role = Column(String(20), nullable=False, index=True)  # bu_head | engineer
    recipient_user_id = Column(Integer, nullable=True, index=True)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    project_id = Column(Integer, nullable=True, index=True)
    actor_name = Column(String(150), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime, server_default=func.now())


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
    created_by_user_id = Column(Integer, nullable=True)  # an engineer deletes only subtasks they created
    estimated_hours = Column(Integer, nullable=True, default=None)
    deliverable_status = Column(String(40), nullable=False, default=TO_DO)
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=True)
    start_date = Column(Date, nullable=True)
    target_due_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    actual_start_datetime = Column(UTCDateTime, nullable=True)
    actual_end_datetime = Column(UTCDateTime, nullable=True)
    phase = Column(String(50), nullable=True, index=True)
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())

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
    created_at = Column(UTCDateTime, server_default=func.now())


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
    created_at = Column(UTCDateTime, server_default=func.now())


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
    requested_at = Column(UTCDateTime, server_default=func.now())
    decided_at = Column(UTCDateTime, nullable=True)


class TimeLogEntry(Base):
    """
    One day's hours of one engineer on one subtask, banked by Logout
    (app/services/tracking.py) and approved per day by the task's lead or the
    BU Head (app/services/hours_review.py). The weekly timesheet is the sum of
    its days. Scoped server-side by the role on the project.
    """
    __tablename__ = "time_log_entries"
    __table_args__ = (
        UniqueConstraint("project_id", "task_id", "employee_id", "work_date", name="uq_time_log_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    task_name = Column(String(255), nullable=True)  # set when the subtask is deleted: the hours stay
    task_lead_user_id = Column(Integer, nullable=True)  # ... and so does the lead who reviews them
    employee_id = Column(Integer, nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    hours = Column(Float, nullable=False, default=0)
    trimmed_hours = Column(Float, nullable=True)  # logged but left out by "approve up to the last visit"
    approval_status = Column(String(20), nullable=False, default="pending_review", index=True)
    reviewed_by = Column(String(150), nullable=True)
    reviewed_by_user_id = Column(Integer, nullable=True)  # hours the BU Head rejected: only the BU Head re-approves
    reviewed_at = Column(UTCDateTime, nullable=True)
    review_reason = Column(Text, nullable=True)  # why approved hours were taken back, or a rejection note
    reapproved_at = Column(UTCDateTime, nullable=True)  # approved again once: then only the BU Head decides
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, onupdate=func.now())


class TimeSession(Base):
    """
    One Login → Logout period of an engineer on a subtask (app/services/tracking.py).

    Worked time is logout_at − login_at, set when the session ends; all of it
    is banked. `last_seen_at` is the browser's last heartbeat: a long silence
    (laptop off or asleep) closes the session there and a new one resumes.
    `last_active_at` is the engineer's last visit to the app; past 8 h in a
    day, 30 minutes without one closes the session there (`ended_by`).
    `version_id` makes concurrent heartbeats from two tabs safe.
    """
    __tablename__ = "time_sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    subtask_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False, index=True)
    login_at = Column(UTCDateTime, nullable=False, index=True)
    last_seen_at = Column(UTCDateTime, nullable=False)
    last_active_at = Column(UTCDateTime, nullable=True)  # last click, key press or tab switch
    logout_at = Column(UTCDateTime, nullable=True)
    active_seconds = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active", index=True)
    ended_by = Column(String(20), nullable=True)  # engineer | laptop_off | no_visit | subtask_deleted | subtask_done | project_archived
    version_id = Column(Integer, nullable=False)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, onupdate=func.now())

    __mapper_args__ = {"version_id_col": version_id}


class TeamMember(Base):
    """A lead's team on a project (decided 2026-10-07): the people they picked from everyone
    in the app. Assign Engineer on Resource Booking lists only them, so the lead doesn't
    search the whole company each time. Each lead of a project keeps their own team."""
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("project_id", "lead_user_id", "employee_id", name="uq_team_member"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    lead_user_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(Integer, nullable=False)
    added_at = Column(UTCDateTime, server_default=func.now())
