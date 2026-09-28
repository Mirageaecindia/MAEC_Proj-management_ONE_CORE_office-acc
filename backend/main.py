import logging
import os
import csv
import io
import re
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user
from database import SessionLocal, engine, get_db
from app.api import api_router
from app.core.errors import register_exception_handlers
from app.core.migrations import migrate
from app.core.security import require_role
from app.domain.calendar import distribute_hours_over_months as _distribute_hours_over_months
from app.domain.calendar import month_key as _get_month_key
from app.domain.timesheets import entry_total as time_entry_total
from app.domain.wbs import TO_DO, is_finished
from app.services.allocation import allocated_pct, over_capacity_message
from app.services.access import (
    NOT_PROJECT_LEAD,
    engineer_wbs_condition,
    lead_employee_ids,
    lead_project_ids,
    leads_any_project,
    project_role,
    user_can_access_project,
    visible_project_ids,
)
from app.services.booking_approval import BOOKING_APPROVAL_LABELS, booking_approval_status
from app.services.governance import extension_request_output, find_pending_extension_request
from app.services.metrics import executive_dashboard_data
from app.services.governance_monitor import enforce_governance
from app.services.notifications import EXTENSION_REQUESTED, create_bu_head_notification

logger = logging.getLogger(__name__)

STAFF = {"engineer"}  # everyone but the BU Head; leading a project is a role on the project, not an account
LEAD_ROW = "Lead assignments are set by the BU Head on the project, not here."
LEAD_HOURS_BU_HEAD = "A project lead's hours are approved by the BU Head."
ENGINEER_HOURS_LEAD = "An engineer's hours are approved by the project's leads."


def require_hours_reviewer(db: Session, user: models.User, project_id: int, employee_id: int) -> None:
    """Who reviews whose hours: the BU Head reviews the project's leads; a lead of the project reviews
    the engineers (never themselves)."""
    lead_hours = employee_id in lead_employee_ids(db, project_id)
    if user.role == "bu_head":
        if not lead_hours:
            raise HTTPException(status_code=403, detail=ENGINEER_HOURS_LEAD)
    elif project_role(db, user, project_id) != "lead":
        raise HTTPException(status_code=403, detail=NOT_PROJECT_LEAD)
    elif lead_hours:
        raise HTTPException(status_code=403, detail=LEAD_HOURS_BU_HEAD)


def refuse_lead_as_resource(db: Session, project_id: int, employee: models.Employee) -> None:
    """A project's lead can't also be booked on it as an engineer: their lead assignment covers their work there."""
    if employee.id in lead_employee_ids(db, project_id):
        raise HTTPException(
            status_code=400,
            detail=f"{employee.name} leads this project; their lead assignment already covers their work here.",
        )

# Schema: Alembic migrations in migrations/, applied at startup (app/core/migrations.py).
migrate(engine)

app = FastAPI(title="ProManage API", version="1.0.0")

# Allow the React dev servers to call this API. The app pins two dev ports
# (5173 = BU Head, 5174 = Lead) and is opened via localhost or 127.0.0.1.
# Any local dev origin (any port) is accepted; otherwise the browser blocks
# the preflight and fetch() fails with the generic "Failed to fetch", which
# surfaces as an error banner plus "No projects yet" on the dashboards.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Error-Code"],
)

# No public static file mount: uploaded files (e.g. SOWs) must be served by an
# authenticated endpoint that checks project access (docs/TODO.md S5/C3).

# Auth and BU Head endpoints live in the app package and MUST be mounted here,
# before any @app route below; tests/test_route_ownership.py enforces this.
# Never re-add BU Head endpoints or the helpers imported above to this file.
register_exception_handlers(app)
app.include_router(api_router)


def seed_project_leads(db: Session):
    if db.query(models.ProjectLead).count() == 0:
        db.add_all([
            models.ProjectLead(name="Rahul Sharma", title="Senior MEP Lead"),
            models.ProjectLead(name="Anita Kumar", title="HVAC Engineer"),
            models.ProjectLead(name="Sanjay Patel", title="Electrical Engineer"),
            models.ProjectLead(name="Neha Rao", title="BIM Coordinator"),
        ])
        db.commit()


with SessionLocal() as _db:
    seed_project_leads(_db)
    if _db.query(models.Employee).count() == 0:
        csv_path = os.path.join(os.path.dirname(__file__), "data", "employee_leads.csv")
        if os.path.exists(csv_path):
            with open(csv_path, newline="", encoding="utf-8-sig") as employee_file:
                employees = []
                for row in csv.DictReader(employee_file):
                    code = (row.get("Emp No") or "").strip()
                    name = (row.get("Emp Name") or "").strip()
                    title = (row.get("Designation") or "").strip()
                    if code and name and title:
                        employees.append(models.Employee(employee_code=code, name=name, role_title=title, discipline=title))
                _db.add_all(employees)
                _db.commit()


def parse_legacy_requested_hours(comments: str) -> float:
    match = re.search(r"extend limit by\s+([0-9]+(?:\.[0-9]+)?)\s*hours", comments, re.IGNORECASE)
    if not match:
        raise HTTPException(
            status_code=422,
            detail="Requested additional hours must be included in the extension request.",
        )
    return float(match.group(1))


def create_extension_request(
    db: Session,
    project: models.Project,
    user: models.User,
    requested_hours: float,
    justification: Optional[str],
) -> models.ExtensionRequest:
    # Only a Lead allocated to this project may ask the BU Head for extra hours.
    if not user_can_access_project(db, user, project):
        raise HTTPException(status_code=403, detail="You do not have access to this project.")
    if not user.full_name:
        raise HTTPException(status_code=400, detail="Lead identity is required.")
    if find_pending_extension_request(db, project.id):
        raise HTTPException(status_code=409, detail="This project already has a pending extension request.")

    request = models.ExtensionRequest(
        project_id=project.id,
        requested_by=user.full_name,
        requested_by_user_id=user.id,
        requested_hours=requested_hours,
        justification=justification,
        status="pending",
    )
    db.add(request)
    db.flush()

    data = executive_dashboard_data(db, project)
    action = models.GovernanceAction(
        project_id=project.id,
        action="extension_request",
        discipline=data["governance_status"]["max_discipline"],
        consumption_pct=data["governance_status"]["consumption_pct"],
        threshold_pct=project.governance_threshold_pct,
        consumption_hours=data["summary"]["approved_hours"],
        comments=justification,
        created_by=user.full_name,
        extension_request_id=request.id,
        requested_hours=request.requested_hours,
    )
    project.extension_status = "pending"
    db.add(action)
    create_bu_head_notification(
        db,
        EXTENSION_REQUESTED,
        "Extension request pending approval",
        f"{user.full_name} requested {requested_hours:g} extra hours on '{project.project_name}'.",
        project_id=project.id,
        actor_name=user.full_name,
    )
    db.commit()
    db.refresh(request)
    return request


def lead_node_condition(user: models.User):
    """SQL condition: WBS node assigned to a lead by their real user id."""
    conditions = [models.WbsNode.assigned_lead_user_id == user.id]
    if user.full_name:
        conditions.append(
            and_(models.WbsNode.assigned_lead_user_id.is_(None), models.WbsNode.assigned_lead == user.full_name)
        )
    return or_(*conditions)


def node_assigned_to_engineer(node: models.WbsNode, user: models.User) -> bool:
    """True if the engineer owns this WBS node by their real employee id only."""
    return bool(user.employee_id and node.assigned_engineer_id == user.employee_id)


def node_assigned_to_lead(node: models.WbsNode, user: models.User) -> bool:
    """True if this lead account is the assigned lead for a WBS node.

    Primary matching is by the real user id (assigned_lead_user_id); a
    name-based fallback only applies to legacy rows where that id is NULL.
    """
    if node.assigned_lead_user_id is not None:
        return node.assigned_lead_user_id == user.id
    return bool(user.full_name and node.assigned_lead == user.full_name)


def incomplete_subtasks(db: Session, node: models.WbsNode) -> List[models.WbsNode]:
    """Direct child subtasks of a node whose deliverable_status is not 'Done'."""
    return (
        db.query(models.WbsNode)
        .filter_by(parent_id=node.id)
        .filter(models.WbsNode.deliverable_status != "Done")
        .order_by(models.WbsNode.wbs_code, models.WbsNode.id)
        .all()
    )


def subtask_gate_error(blocking: List[models.WbsNode]) -> str:
    """Clear message naming which subtask(s) still block task submission."""
    if len(blocking) == 1:
        return f"Cannot submit for approval — 1 subtask ('{blocking[0].task_name}') is still not marked Done."
    names = ", ".join(f"'{subtask.task_name}'" for subtask in blocking)
    return f"Cannot submit for approval — {len(blocking)} subtasks are still not marked Done: {names}."


@app.get("/api/engineers", response_model=List[schemas.EngineerOut])
def list_engineers(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"lead", "bu_head", "engineer"})
    return db.query(models.Employee).order_by(models.Employee.name).all()


@app.get("/api/employees", response_model=List[schemas.EngineerOut])
def list_employees(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "bu_head" and not leads_any_project(db, user):
        raise HTTPException(status_code=403, detail=NOT_PROJECT_LEAD)
    return db.query(models.Employee).order_by(models.Employee.name).all()


@app.get("/api/projects/{project_id}/booked-engineers", response_model=List[schemas.EngineerOut])
def list_project_booked_engineers(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Engineers actually booked onto this project via Resource Booking.

    This powers the WBS 'Assign Engineer' dropdown: only these engineers are
    eligible for NEW task/subtask assignments, not the global employee list.
    Existing WBS assignments are never touched by booking changes — removing a
    booking does not auto-unassign tasks already handed out.
    """
    project_and_role(db, project_id, user, allowed={"bu_head", "lead"})
    booked = (
        db.query(models.Employee)
        .join(models.ResourceBooking, models.ResourceBooking.employee_id == models.Employee.id)
        .filter(models.ResourceBooking.project_id == project_id)
        .order_by(models.Employee.name)
        .all()
    )
    return booked


def _parse_iso_date(value) -> Optional[date]:
    """Parse an ISO 'YYYY-MM-DD' string (or date) into a date instance; None-safe."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def booking_effective_dates(db: Session, booking: models.ResourceBooking):
    """Return (start, end) for a booking, preferring the stored allocation
    date range and backfilling from the engineer's WBS node dates on the same
    project where determinable. Never fabricates a range."""
    start = booking.start_date
    end = booking.end_date
    if start and end:
        return start, end

    node_start = None
    node_end = None
    nodes = (
        db.query(models.WbsNode)
        .filter(
            models.WbsNode.project_id == booking.project_id,
            models.WbsNode.assigned_engineer_id == booking.employee_id,
        )
        .all()
    )
    for node in nodes:
        if node.start_date and (node_start is None or node.start_date < node_start):
            node_start = node.start_date
        bound = node.end_date or node.target_due_date
        if bound and (node_end is None or bound > node_end):
            node_end = bound

    return start or node_start, end or node_end


def last_day_of_month(value: date) -> date:
    import calendar
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def booking_output(db: Session, booking: models.ResourceBooking):
    employee = db.query(models.Employee).filter_by(id=booking.employee_id).first()
    utilization = float(booking.utilization_rate or 0)
    return {
        "id": booking.id,
        "employee_id": booking.employee_id,
        "employee_name": employee.name if employee else "Unknown",
        "employee_code": employee.employee_code if employee else "",
        "discipline": employee.discipline if employee else "",
        "role_title": employee.role_title if employee else "",
        "role": booking.role,
        "planned_hours": booking.planned_hours,
        "utilization_rate": utilization,
        "start_date": booking.start_date.isoformat() if booking.start_date else None,
        "end_date": booking.end_date.isoformat() if booking.end_date else None,
        "total_allocation_pct": float(
            allocated_pct(db, booking.employee_id, booking.start_date, booking.end_date)
        ),  # busiest day during this booking
        "cost_per_hour": 0,
        "total_cost": 0,
        "bench_status": "Fully Booked" if utilization >= 100 else "Near Capacity" if utilization >= 80 else "Available Bench",
        "approval_status": booking.approval_status,
        "submitted_at": booking.submitted_at.isoformat() if booking.submitted_at else None,
        "approved_at": booking.approved_at.isoformat() if booking.approved_at else None,
    }


@app.get("/api/projects/{project_id}/resource-bookings")
def list_resource_bookings(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    _, role = project_and_role(db, project_id, user)
    query = db.query(models.ResourceBooking).filter_by(project_id=project_id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter_by(employee_id=user.employee_id)
    bookings = query.all()
    return [booking_output(db, booking) for booking in bookings]


@app.get("/api/resource-bookings/gantt")
def resource_booking_gantt(
    project_id: Optional[int] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Engineer assignment timeline for the Resource Booking page.

    With `project_id` (what the page sends): one entry per engineer booked on
    that project. Without it: every engineer booked on a project the lead leads
    (all projects for the BU Head). Either way each engineer is shown with their
    FULL commitment across all projects, so overlapping assignments are visible.
    Date ranges come from the booking record, falling back to the engineer's
    WBS node dates on that project where determinable.
    """
    if project_id is not None:
        project_and_role(db, project_id, user, allowed={"bu_head", "lead"})
        scoped_bookings = db.query(models.ResourceBooking).filter_by(project_id=project_id).all()
    elif user.role != "bu_head":
        lead_ids = lead_project_ids(db, user)
        if not lead_ids:
            return {"engineers": [], "date_range": {"start": None, "end": None}, "count": 0}
        scoped_bookings = (
            db.query(models.ResourceBooking)
            .filter(models.ResourceBooking.project_id.in_(lead_ids))
            .all()
        )
    else:
        scoped_bookings = db.query(models.ResourceBooking).all()

    employee_ids = {booking.employee_id for booking in scoped_bookings}
    if not employee_ids:
        return {"engineers": [], "date_range": {"start": None, "end": None}, "count": 0}

    # A lead sees each scoped engineer's full commitment across every project.
    all_bookings = (
        db.query(models.ResourceBooking)
        .filter(models.ResourceBooking.employee_id.in_(employee_ids))
        .order_by(models.ResourceBooking.employee_id, models.ResourceBooking.start_date)
        .all()
    )

    employees = {
        employee.id: employee
        for employee in db.query(models.Employee).filter(models.Employee.id.in_(employee_ids)).all()
    }
    project_ids = {booking.project_id for booking in all_bookings}
    projects = {
        project.id: project
        for project in db.query(models.Project).filter(models.Project.id.in_(project_ids or {-1})).all()
    }

    engineers_out = []
    earliest = None
    latest = None
    for employee_id in sorted(employee_ids):
        employee = employees.get(employee_id)
        if employee is None:
            continue
        assignments = []
        for booking in (booking for booking in all_bookings if booking.employee_id == employee_id):
            start, end = booking_effective_dates(db, booking)
            project = projects.get(booking.project_id)
            assignments.append({
                "booking_id": booking.id,
                "project_id": booking.project_id,
                "project_name": project.project_name if project else f"Project #{booking.project_id}",
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "has_date_range": bool(start and end),
                "role": booking.role,
                "utilization_rate": booking.utilization_rate or 0,
                "planned_hours": booking.planned_hours or 0,
                "approval_status": booking.approval_status,
            })
            if start and end:
                if earliest is None or start < earliest:
                    earliest = start
                if latest is None or end > latest:
                    latest = end
        engineers_out.append({
            "employee_id": employee.id,
            "name": employee.name,
            "employee_code": employee.employee_code,
            "role_title": employee.role_title,
            "discipline": employee.discipline,
            "total_allocation_pct": allocated_pct(db, employee.id, None, None),  # their busiest day
            "assignments": assignments,
        })

    engineers_out.sort(key=lambda row: row["name"])

    date_range = {"start": None, "end": None}
    if earliest and latest:
        today = date.today()
        start, end = earliest, latest
        if today < start:
            start = today
        if today > end:
            end = today
        date_range = {
            "start": date(start.year, start.month, 1).isoformat(),
            "end": last_day_of_month(end).isoformat(),
        }

    return {"engineers": engineers_out, "date_range": date_range, "count": len(engineers_out)}


@app.post("/api/projects/{project_id}/resource-bookings")
def create_resource_booking(
    project_id: int,
    payload: dict,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, _ = project_and_role(db, project_id, user, allowed={"lead"})
    employee = db.query(models.Employee).filter_by(id=payload.get("employee_id")).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Engineer not found.")
    refuse_lead_as_resource(db, project_id, employee)
    requested = int(payload.get("utilization_rate", 0))
    start_date = _parse_iso_date(payload.get("start_date"))
    end_date = _parse_iso_date(payload.get("end_date"))
    over = over_capacity_message(db, employee.name, employee.id, requested, start_date, end_date)
    if over:
        raise HTTPException(status_code=400, detail=over, headers={"X-Error-Code": "ALLOCATION_LIMIT"})
    derived_hours = estimated_hours_from_dates(start_date, end_date)
    booking = models.ResourceBooking(
        project_id=project_id,
        employee_id=employee.id,
        planned_hours=derived_hours if derived_hours is not None else int(payload.get("planned_hours", 0)),
        utilization_rate=requested,
        start_date=start_date,
        end_date=end_date,
        approval_status="draft",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking_output(db, booking)


@app.put("/api/projects/{project_id}/resource-bookings/{booking_id}")
def update_resource_booking(
    project_id: int,
    booking_id: int,
    payload: dict,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_and_role(db, project_id, user, allowed={"lead"})
    booking = db.query(models.ResourceBooking).filter_by(id=booking_id, project_id=project_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Resource booking not found.")
    if booking.role == "lead":
        raise HTTPException(status_code=400, detail=LEAD_ROW)
    employee_id = int(payload.get("employee_id", booking.employee_id))
    employee = db.query(models.Employee).filter_by(id=employee_id).first()
    if not employee:
        raise HTTPException(status_code=400, detail="Engineer not found.")
    refuse_lead_as_resource(db, project_id, employee)
    requested = int(payload.get("utilization_rate", booking.utilization_rate or 0))
    start_date = _parse_iso_date(payload["start_date"]) if payload.get("start_date") is not None else booking.start_date
    end_date = _parse_iso_date(payload["end_date"]) if payload.get("end_date") is not None else booking.end_date
    over = over_capacity_message(
        db, employee.name, employee.id, requested, start_date, end_date, exclude_booking_id=booking.id
    )
    if over:
        raise HTTPException(status_code=400, detail=over, headers={"X-Error-Code": "ALLOCATION_LIMIT"})
    booking.employee_id = employee.id
    booking.start_date, booking.end_date = start_date, end_date
    derived_hours = estimated_hours_from_dates(booking.start_date, booking.end_date)
    booking.planned_hours = derived_hours if derived_hours is not None else int(payload.get("planned_hours", booking.planned_hours or 0))
    booking.utilization_rate = requested
    db.commit()
    db.refresh(booking)
    return booking_output(db, booking)


@app.delete("/api/projects/{project_id}/resource-bookings/{booking_id}")
def delete_resource_booking(
    project_id: int,
    booking_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_and_role(db, project_id, user, allowed={"lead"})
    booking = db.query(models.ResourceBooking).filter_by(id=booking_id, project_id=project_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Resource booking not found.")
    if booking.role == "lead":
        raise HTTPException(status_code=400, detail=LEAD_ROW)
    db.delete(booking)
    db.commit()
    return {"ok": True, "deleted_booking_id": booking_id}


@app.post("/api/projects/{project_id}/resource-bookings/submit")
def submit_resource_bookings(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only a lead of this project may submit its bookings to the BU Head.
    project, _ = project_and_role(db, project_id, user, allowed={"lead"})
    bookings = db.query(models.ResourceBooking).filter_by(project_id=project_id, role="engineer").all()
    if not bookings:
        raise HTTPException(status_code=400, detail="Assign at least one engineer before submitting for approval.")
    current = booking_approval_status(db, project_id)
    if current == "pending_approval":
        raise HTTPException(status_code=409, detail="This resource booking is already pending approval.")
    if current == "approved":
        raise HTTPException(status_code=409, detail="This resource booking has already been approved.")

    now = datetime.now(timezone.utc)
    for booking in bookings:
        booking.approval_status = "pending_approval"
        booking.submitted_at = now
    create_bu_head_notification(
        db,
        notification_type="resource_booking_approval",
        title="Resource booking pending approval",
        message=f"Resource booking for '{project.project_name}' has been submitted for approval.",
        project_id=project.id,
        actor_name=user.full_name or user.username,
    )
    db.commit()
    return {
        "status": "pending_approval",
        "status_label": BOOKING_APPROVAL_LABELS["pending_approval"],
    }


def node_level(db: Session, node: models.WbsNode) -> int:
    level = 1
    parent_id = node.parent_id
    while parent_id:
        parent = db.query(models.WbsNode).filter_by(id=parent_id).first()
        if not parent:
            break
        level += 1
        parent_id = parent.parent_id
    return level


def node_output(db: Session, node: models.WbsNode):
    engineer = db.query(models.Employee).filter_by(id=node.assigned_engineer_id).first() if node.assigned_engineer_id else None
    parent_node = None
    if node.parent_id:
        parent_node = db.query(models.WbsNode).filter_by(id=node.parent_id).first()
    return schemas.WbsNodeOut(
        id=node.id,
        project_id=node.project_id,
        parent_id=node.parent_id,
        wbs_code=node.wbs_code,
        task_name=node.task_name,
        assigned_lead=node.assigned_lead,
        assigned_lead_user_id=node.assigned_lead_user_id,
        assigned_engineer_id=node.assigned_engineer_id,
        assigned_engineer_name=engineer.name if engineer else None,
        estimated_hours=node.estimated_hours,
        deliverable_status=node.deliverable_status,
        start_date=node.start_date,
        target_due_date=node.target_due_date,
        end_date=node.end_date,
        phase=node.phase,
        level=node_level(db, node),
    )


def node_type(node: models.WbsNode) -> str:
    return "subtask" if node.parent_id else "task"


def node_status_flow(node: models.WbsNode) -> list:
    return schemas.WBS_STATUS_FLOWS.get(node_type(node), schemas.WBS_TASK_STATUSES)


def validate_status_transition(current_status: str, new_status: str, node: models.WbsNode) -> Optional[str]:
    mapped_current = map_status_for_display(current_status)
    flow = node_status_flow(node)
    if new_status not in flow:
        return f"Status '{new_status}' is not valid for this node type. Valid statuses: {', '.join(flow)}"
    if mapped_current == new_status:
        return None
    if new_status not in flow:
        return f"Status '{new_status}' is not in the allowed status flow."
    current_idx = flow.index(mapped_current) if mapped_current in flow else -1
    new_idx = flow.index(new_status)
    if new_idx != current_idx + 1:
        next_status = flow[current_idx + 1] if current_idx + 1 < len(flow) else 'end of flow'
        return f"Cannot move from '{mapped_current}' to '{new_status}'. Next valid status: '{next_status}'"
    return None


def validate_node_payload(db: Session, project_id: int, payload: schemas.WbsNodeBase):
    if payload.parent_id is not None:
        parent = db.query(models.WbsNode).filter_by(id=payload.parent_id, project_id=project_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent WBS node does not belong to this project.")
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=400,
                detail="A subtask cannot have its own subtasks. Only main tasks can have subtasks.",
            )
    if payload.assigned_engineer_id is not None and not db.query(models.Employee).filter_by(id=payload.assigned_engineer_id).first():
        raise HTTPException(status_code=400, detail="Engineer not found.")
    if payload.assigned_lead_user_id is not None and not db.query(models.User).filter(models.User.id == payload.assigned_lead_user_id, models.User.role != "bu_head").first():
        raise HTTPException(status_code=400, detail="Assigned lead user not found.")


@app.get("/api/projects/{project_id}/wbs-structure", response_model=List[schemas.WbsNodeOut])
def list_wbs_structure(
    project_id: int,
    include_ancestors: bool = False,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, role = project_and_role(db, project_id, user)
    query = db.query(models.WbsNode).filter_by(project_id=project_id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        assigned_nodes = query.filter(
            engineer_wbs_condition(user.employee_id)
        ).all()
        if not include_ancestors:
            return [node_output(db, node) for node in assigned_nodes]

        nodes_by_id = {node.id: node for node in assigned_nodes}
        pending_nodes = list(assigned_nodes)
        while pending_nodes:
            node = pending_nodes.pop()
            parent_id = node.parent_id
            if parent_id and parent_id not in nodes_by_id:
                parent = db.query(models.WbsNode).filter_by(
                    id=parent_id,
                    project_id=project_id,
                ).first()
                if parent:
                    nodes_by_id[parent.id] = parent
                    pending_nodes.append(parent)
        scoped_nodes = list(nodes_by_id.values())
    else:
        scoped_nodes = query.order_by(models.WbsNode.wbs_code).all()
    return [node_output(db, node) for node in scoped_nodes]


def time_entry_hours_by_month(entry) -> dict[str, float]:
    """Bucket a weekly time entry's hours into the REAL month each day was worked.

    A weekly entry stores one column per weekday relative to ``week_start_date``,
    so the actual calendar date of every logged day is recoverable. Bucketing by
    the week's start date instead misfiles any day that falls in a later month
    than the Monday the week began on: the Thursday and Friday of a week starting
    Mon 31 Aug are September work, not August work. Grouping per day keeps every
    month correct even when a week straddles a month boundary.
    """
    from datetime import timedelta

    buckets: dict[str, float] = {}
    if not entry.week_start_date:
        return buckets
    for offset, field in enumerate(models.DAY_FIELDS):
        hours = float(getattr(entry, field, 0) or 0)
        if hours <= 0:
            continue
        worked_on = entry.week_start_date + timedelta(days=offset)
        key = _get_month_key(worked_on)
        buckets[key] = round(buckets.get(key, 0.0) + hours, 4)
    return buckets


def time_entry_output(db: Session, entry: models.TimeLogEntry):
    task = db.query(models.WbsNode).filter_by(id=entry.task_id).first()
    employee = db.query(models.Employee).filter_by(id=entry.employee_id).first()
    return schemas.TimeLogEntryOut(
        id=entry.id,
        project_id=entry.project_id,
        task_id=entry.task_id,
        wbs_code=task.wbs_code if task else None,
        task_name=task.task_name if task else "",
        employee_id=entry.employee_id,
        employee_name=employee.name if employee else "",
        week_start_date=entry.week_start_date,
        mon_hours=entry.mon_hours,
        tue_hours=entry.tue_hours,
        wed_hours=entry.wed_hours,
        thu_hours=entry.thu_hours,
        fri_hours=entry.fri_hours,
        sat_hours=entry.sat_hours,
        sun_hours=entry.sun_hours,
        total_hours=round(time_entry_total(entry), 2),
        approval_status=entry.approval_status,
        reviewed_by=entry.reviewed_by,
        reviewed_at=entry.reviewed_at,
    )


def scoped_wbs_tasks(
    db: Session,
    project_id: int,
    user: models.User,
    role: str,
):
    """The WBS nodes in the user's scope on this project, for their role on it."""
    query = db.query(models.WbsNode).filter_by(project_id=project_id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter(
            engineer_wbs_condition(user.employee_id)
        )
    elif role == "lead":
        query = query.filter(lead_node_condition(user))
    return query.order_by(models.WbsNode.wbs_code).all()


@app.get("/api/projects/{project_id}/timesheet")
def list_timesheet_entries(
    project_id: int,
    week_start: Optional[str] = None,
    source: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, role = project_and_role(db, project_id, user)
    query = db.query(models.TimeLogEntry).filter_by(project_id=project_id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter_by(employee_id=user.employee_id)
    elif role == "lead":
        lead_tasks = scoped_wbs_tasks(db, project_id, user, role)
        task_ids = [task.id for task in lead_tasks]
        query = query.filter(models.TimeLogEntry.task_id.in_(task_ids)) if task_ids else query.filter(models.TimeLogEntry.id < 0)
    if week_start:
        query = query.filter_by(week_start_date=date.fromisoformat(week_start))
    if source == "tracking":
        # The Weekly Hours Logging sheet is fed exclusively by automatic
        # subtask tracking: only engineer subtasks (never main tasks) that
        # actually have tracked working time are shown.
        subtask_ids = [
            node.id
            for node in db.query(models.WbsNode)
            .filter(models.WbsNode.project_id == project_id, models.WbsNode.parent_id.isnot(None))
            .all()
        ]
        tracked = or_(*[getattr(models.TimeLogEntry, field) > 0 for field in models.DAY_FIELDS])
        query = query.filter(
            models.TimeLogEntry.task_id.in_(subtask_ids) if subtask_ids else models.TimeLogEntry.id < 0,
            tracked,
        )
    return [time_entry_output(db, entry) for entry in query.order_by(models.TimeLogEntry.week_start_date).all()]


# --- Weekly-hours submission & approval --------------------------------------
# The Weekly Hours section keys off a per-(engineer, week) submission record
# that the ENGINEER creates. Engineer submits -> Lead approves/rejects, and the
# Lead can only review a week whose status is exactly 'submitted' (enforced
# here server-side, independent of any frontend button visibility).

WEEKLY_HOURS_STATUS_LABELS = {
    "not_submitted": "Not Submitted",
    "submitted": "Submitted for Approval",
    "approved": "Approved",
    "rejected": "Rejected",
}


def weekly_submission_output(
    db: Session, submission: models.WeeklyHoursSubmission, lead_ids: Optional[set] = None
) -> dict:
    """`lead_hours`: these are a project lead's hours, so the BU Head reviews them, not a lead."""
    employee = db.query(models.Employee).filter_by(id=submission.employee_id).first()
    if lead_ids is None:
        lead_ids = lead_employee_ids(db, submission.project_id)
    return {
        "id": submission.id,
        "project_id": submission.project_id,
        "employee_id": submission.employee_id,
        "employee_name": employee.name if employee else "",
        "lead_hours": submission.employee_id in lead_ids,
        "week_start_date": submission.week_start_date.isoformat(),
        "status": submission.status,
        "status_label": WEEKLY_HOURS_STATUS_LABELS.get(submission.status, submission.status),
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "reviewed_by": submission.reviewed_by,
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
    }


def weekly_submission_for(
    db: Session, project_id: int, employee_id: int, week: date
) -> Optional[models.WeeklyHoursSubmission]:
    return (
        db.query(models.WeeklyHoursSubmission)
        .filter_by(project_id=project_id, employee_id=employee_id, week_start_date=week)
        .first()
    )


def weekly_hours_visible_employee_ids(
    db: Session, project_id: int, week: date, user: models.User, role: str
) -> Optional[set]:
    """Employee ids whose weekly-hours submissions this user may see or review.

    Engineer: only their own real employee id. Lead: engineers assigned to a
    WBS node in the lead's scope, plus engineers who logged hours on those
    scoped tasks that week (mirrors the timesheet scoping). BU Head: None,
    meaning unrestricted.
    """
    if role == "bu_head":
        return None
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        return {user.employee_id}
    tasks = scoped_wbs_tasks(db, project_id, user, role)
    visible = {task.assigned_engineer_id for task in tasks if task.assigned_engineer_id}
    task_ids = [task.id for task in tasks]
    if task_ids:
        logged = (
            db.query(models.TimeLogEntry.employee_id)
            .filter(
                models.TimeLogEntry.project_id == project_id,
                models.TimeLogEntry.task_id.in_(task_ids),
                models.TimeLogEntry.week_start_date == week,
            )
            .distinct()
            .all()
        )
        visible.update(row[0] for row in logged)
    return visible


def project_and_role(
    db: Session, project_id: int, user: models.User, allowed: Optional[set] = None
) -> tuple[models.Project, str]:
    """The project and the user's role on it (bu_head, lead or engineer).

    404 when the project doesn't exist; 403 when the user has no role on it, or
    a role outside `allowed`. Lead and engineer are roles on a project, not
    account types: the same person can lead one project and work on another.
    """
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    role = project_role(db, user, project_id)
    if role is None:
        raise HTTPException(status_code=403, detail="You do not have access to this project.")
    if allowed is not None and role not in allowed:
        detail = NOT_PROJECT_LEAD if allowed == {"lead"} else "This action is not allowed for your role on this project."
        raise HTTPException(status_code=403, detail=detail)
    return project, role


def require_project_access(db: Session, project_id: int, user: models.User) -> models.Project:
    return project_and_role(db, project_id, user)[0]


@app.get("/api/projects/{project_id}/weekly-hours-submissions")
def list_weekly_hours_submissions(
    project_id: int,
    week_start: str,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, role = project_and_role(db, project_id, user)
    week = date.fromisoformat(week_start)
    visible = weekly_hours_visible_employee_ids(db, project_id, week, user, role)
    query = db.query(models.WeeklyHoursSubmission).filter_by(project_id=project_id, week_start_date=week)
    if visible is not None:
        query = query.filter(
            models.WeeklyHoursSubmission.employee_id.in_(visible) if visible else models.WeeklyHoursSubmission.id < 0
        )
    lead_ids = lead_employee_ids(db, project_id)  # once for the whole list
    return [
        weekly_submission_output(db, submission, lead_ids)
        for submission in query.order_by(models.WeeklyHoursSubmission.employee_id).all()
    ]


@app.post("/api/projects/{project_id}/weekly-hours/submit")
def submit_weekly_hours(
    project_id: int,
    payload: schemas.WeeklyHoursActionIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, STAFF)  # own work: the employee link below is the real gate
    project = require_project_access(db, project_id, user)
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    if project.timesheets_soft_locked:
        raise HTTPException(
            status_code=409,
            detail="Timesheets are soft-locked by the BU Head — weekly submissions are on hold.",
        )
    # Only a week with real tracked log hours can be submitted for approval;
    # mirrors the tracking filter of the timesheet endpoint so the UI's
    # "Submit for Approval" availability always matches the server-side rule.
    tracked = or_(*[getattr(models.TimeLogEntry, field) > 0 for field in models.DAY_FIELDS])
    eligible = (
        db.query(models.TimeLogEntry)
        .filter(
            models.TimeLogEntry.project_id == project_id,
            models.TimeLogEntry.employee_id == user.employee_id,
            models.TimeLogEntry.week_start_date == payload.week_start_date,
            tracked,
        )
        .first()
    )
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail="This week has no logged hours — nothing to submit for approval.",
        )
    # An engineer can only ever submit their OWN weekly hours; any employee_id
    # in the payload is ignored.
    submission = weekly_submission_for(db, project_id, user.employee_id, payload.week_start_date)
    now = datetime.now(timezone.utc)
    if submission:
        if submission.status == "approved":
            raise HTTPException(
                status_code=409,
                detail="This week's hours are already approved — a resubmission is not allowed.",
            )
        submission.status = "submitted"
        submission.submitted_at = now
        submission.reviewed_by = None
        submission.reviewed_at = None
    else:
        submission = models.WeeklyHoursSubmission(
            project_id=project_id,
            employee_id=user.employee_id,
            week_start_date=payload.week_start_date,
            status="submitted",
            submitted_at=now,
        )
        db.add(submission)
    db.commit()
    db.refresh(submission)
    return weekly_submission_output(db, submission)


def lead_review_weekly_hours(
    db: Session, project_id: int, action: str, payload: schemas.WeeklyHoursActionIn, user: models.User
):
    if not user.full_name:
        raise HTTPException(status_code=400, detail="Lead identity is required.")
    project, role = project_and_role(db, project_id, user, allowed={"lead", "bu_head"})
    if project.timesheets_soft_locked:
        raise HTTPException(
            status_code=409,
            detail="Timesheets are soft-locked by the BU Head — approvals are on hold.",
        )
    if payload.employee_id is None:
        raise HTTPException(status_code=400, detail="employee_id is required to review weekly hours.")
    require_hours_reviewer(db, user, project_id, payload.employee_id)
    submission = weekly_submission_for(db, project_id, payload.employee_id, payload.week_start_date)
    if not submission:
        raise HTTPException(
            status_code=409,
            detail="This week's hours have not been submitted for approval yet.",
        )
    if submission.status != "submitted":
        raise HTTPException(
            status_code=409,
            detail="Only weekly hours that are 'Submitted for Approval' can be approved or rejected.",
        )
    visible = weekly_hours_visible_employee_ids(db, project_id, payload.week_start_date, user, role)
    if visible is not None and submission.employee_id not in visible:
        raise HTTPException(status_code=403, detail="These weekly hours are outside your lead scope.")
    submission.status = action
    submission.reviewed_by = user.full_name
    submission.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    enforce_governance(db, project_id)  # usage = approved hours: alerts / auto-lock
    db.refresh(submission)
    return weekly_submission_output(db, submission)


@app.post("/api/projects/{project_id}/weekly-hours/approve")
def approve_weekly_hours(
    project_id: int,
    payload: schemas.WeeklyHoursActionIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return lead_review_weekly_hours(db, project_id, "approved", payload, user)


@app.post("/api/projects/{project_id}/weekly-hours/reject")
def reject_weekly_hours(
    project_id: int,
    payload: schemas.WeeklyHoursActionIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return lead_review_weekly_hours(db, project_id, "rejected", payload, user)


@app.get("/api/projects/{project_id}/timeline-logs")
def project_timeline_logs(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, role = project_and_role(db, project_id, user)

    tasks = scoped_wbs_tasks(db, project_id, user, role)
    task_ids = [task.id for task in tasks]

    entries_query = db.query(models.TimeLogEntry).filter_by(project_id=project_id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        entries_query = entries_query.filter_by(employee_id=user.employee_id)
    if task_ids:
        entries_query = entries_query.filter(models.TimeLogEntry.task_id.in_(task_ids))
    else:
        entries_query = entries_query.filter(models.TimeLogEntry.id < 0)
    entries = entries_query.order_by(models.TimeLogEntry.week_start_date).all()

    engineer_ids = {task.assigned_engineer_id for task in tasks if task.assigned_engineer_id}
    engineers = []
    if engineer_ids:
        engineers = db.query(models.Employee).filter(models.Employee.id.in_(engineer_ids)).order_by(models.Employee.name).all()

    task_actual = defaultdict(float)
    for entry in entries:
        task_actual[entry.task_id] += time_entry_total(entry)


    tasks_out = []
    for task in tasks:
        actual = task_actual.get(task.id, 0.0)
        estimated = task.estimated_hours or 0
        is_complete = is_finished(task.deliverable_status)
        if is_complete:
            percent = 100.0
        elif estimated > 0:
            percent = min(100.0, round((actual / estimated) * 100, 1))
        else:
            percent = 0.0
        engineer = db.query(models.Employee).filter_by(id=task.assigned_engineer_id).first() if task.assigned_engineer_id else None
        tasks_out.append({
            "id": task.id,
            "project_id": task.project_id,
            "parent_id": task.parent_id,
            "wbs_code": task.wbs_code,
            "task_name": task.task_name,
            "phase": task.phase,
            "assigned_lead": task.assigned_lead,
            "assigned_engineer_id": task.assigned_engineer_id,
            "assigned_engineer_name": engineer.name if engineer else None,
            "estimated_hours": task.estimated_hours,
            "deliverable_status": task.deliverable_status,
            "is_complete": is_complete,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "target_due_date": task.target_due_date.isoformat() if task.target_due_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "actual_hours": round(actual, 2),
            "percent_complete": percent,
        })

    total_logged = round(sum(time_entry_total(entry) for entry in entries), 2)
    entries_out = [time_entry_output(db, entry) for entry in entries]
    engineer = db.query(models.Employee).filter_by(id=user.employee_id).first() if role == "engineer" and user.employee_id else None

    # Per-phase rollup — the single, shared completion rule: a task counts as
    # complete when its real status reached a terminal state ('Done'/'Approved',
    # plus the legacy 'Completed'); phase % = completed tasks / total tasks.
    # A phase with zero tasks never divides by zero; it just is not reported.
    phase_map = {}
    for task_out in tasks_out:
        phase = task_out.get("phase") or "Space Planning"
        stats = phase_map.setdefault(phase, {"phase": phase, "total_tasks": 0, "completed_tasks": 0})
        stats["total_tasks"] += 1
        if task_out["is_complete"]:
            stats["completed_tasks"] += 1
    phases_out = []
    for stats in phase_map.values():
        total = stats["total_tasks"]
        stats["percent_complete"] = round((stats["completed_tasks"] / total) * 100) if total else 0
        phases_out.append(stats)
    phases_out.sort(key=lambda p: p["phase"])

    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "scope": {
            "role": role,
            "engineer_id": user.employee_id if role == "engineer" else None,
            "engineer_name": engineer.name if engineer else None,
            "lead_name": user.full_name if role == "lead" else None,
        },
        "tasks": tasks_out,
        "phases": phases_out,
        "time_entries": [entry.model_dump() for entry in entries_out],
        "engineers": [
            {"id": e.id, "employee_code": e.employee_code, "name": e.name, "role_title": e.role_title}
            for e in engineers
        ],
        "summary": {
            "total_hours_logged": total_logged,
            "approved_hours": round(sum(time_entry_total(e) for e in entries if e.approval_status == "approved"), 2),
            "pending_hours": round(sum(time_entry_total(e) for e in entries if e.approval_status == "pending_review"), 2),
            "scheduled_hours": sum(task.estimated_hours or 0 for task in tasks),
            "total_tasks": len(tasks),
            "completed_tasks": sum(1 for task in tasks if is_finished(task.deliverable_status)),
            "engineer_count": len(engineers),
        },
    }


@app.get("/api/engineer-performance", response_model=schemas.EngineerPerformanceOut)
def engineer_performance(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, STAFF)  # own work: the employee link below is the real gate
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    employee = db.query(models.Employee).filter_by(id=user.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found for this account.")

    nodes = []
    entries = []
    approved_ids = visible_project_ids(db, user)
    if approved_ids:
        nodes = (
            db.query(models.WbsNode)
            .filter(
                engineer_wbs_condition(user.employee_id),
                models.WbsNode.project_id.in_(approved_ids),
            )
            .order_by(models.WbsNode.wbs_code)
            .all()
        )
        entries = (
            db.query(models.TimeLogEntry)
            .filter(
                models.TimeLogEntry.employee_id == user.employee_id,
                models.TimeLogEntry.project_id.in_(approved_ids),
            )
            .order_by(models.TimeLogEntry.week_start_date.desc())
            .all()
        )
    node_by_id = {node.id: node for node in nodes}
    project_ids = {node.project_id for node in nodes}
    projects = (
        db.query(models.Project)
        .filter(models.Project.id.in_(project_ids or {-1}))
        .all()
        if project_ids
        else []
    )
    project_by_id = {project.id: project for project in projects}
    project_names = {project.id: project.project_name for project in projects}

    per_project = {}
    for project_id in project_ids:
        per_project[project_id] = {
            "project_id": project_id,
            "project_name": project_names.get(project_id),
            "scheduled_hours": 0,
            "logged_hours": 0.0,
            "approved_hours": 0.0,
            "pending_hours": 0.0,
            "total_tasks": 0,
            "completed_tasks": 0,
        }
    for node in nodes:
        row = per_project[node.project_id]
        row["scheduled_hours"] += node.estimated_hours or 0
        row["total_tasks"] += 1
        if is_finished(node.deliverable_status):
            row["completed_tasks"] += 1

    for entry in entries:
        row = per_project.get(entry.project_id)
        if not row:
            continue
        total = time_entry_total(entry)
        row["logged_hours"] = round(row["logged_hours"] + total, 2)
        if entry.approval_status == "approved":
            row["approved_hours"] = round(row["approved_hours"] + total, 2)
        elif entry.approval_status == "pending_review":
            row["pending_hours"] = round(row["pending_hours"] + total, 2)

    total_logged = round(sum(time_entry_total(entry) for entry in entries), 2)
    approved_hours = round(sum(time_entry_total(e) for e in entries if e.approval_status == "approved"), 2)
    pending_hours = round(sum(time_entry_total(e) for e in entries if e.approval_status == "pending_review"), 2)
    scheduled_hours = sum(node.estimated_hours or 0 for node in nodes)

    recent_entries = [
        {
            "id": entry.id,
            "project_name": project_names.get(entry.project_id),
            "task_name": node_by_id[entry.task_id].task_name if entry.task_id in node_by_id else None,
            "week_start_date": entry.week_start_date.isoformat() if entry.week_start_date else None,
            "hours": round(time_entry_total(entry), 2),
            "approval_status": entry.approval_status,
        }
        for entry in entries[:10]
    ]

    return {
        "summary": {
            "name": employee.name,
            "role_title": employee.role_title,
            "discipline": employee.discipline or "—",
            "total_tasks": len(nodes),
            "completed_tasks": sum(1 for node in nodes if is_finished(node.deliverable_status)),
            "scheduled_hours": scheduled_hours,
            "logged_hours": total_logged,
            "approved_hours": approved_hours,
            "pending_hours": pending_hours,
            "completion_pct": round((sum(1 for node in nodes if is_finished(node.deliverable_status)) / len(nodes)) * 100) if nodes else 0,
            "allocation_pct": round((total_logged / scheduled_hours) * 100) if scheduled_hours else 0,
        },
        "projects": [row for row in per_project.values()],
        "recent_entries": recent_entries,
    }


def engineer_dashboard_data(db: Session, employee_id: int, approved_ids: set[int], project_id: int | None = None):
    """Compute engineer-scoped dashboard metrics from approved time entries."""
    from datetime import datetime, date
    from collections import defaultdict
    import calendar

    # WBS nodes assigned to this person (by employee id only) within
    # `approved_ids`: the projects they lead or are approved to work on.
    # Unapproved projects are never surfaced through their dashboard.
    if not approved_ids:
        return {
            "summary": {
                "total_hours_consumption": 0.0,
                "total_hours_scheduled": 0,
                "total_hours_approved": 0.0,
                "total_hours_pending": 0.0,
                "consumption_pct": 0.0,
                "governance_consumption_pct": 0.0,
                "governance_status": "normal",
                "governance_threshold_pct": None,
                "governance_exceeded": False,
                "spi_value": None,
                "spi_note": "No assigned tasks.",
                "total_tasks": 0,
                "started_tasks": 0,
                "completed_tasks": 0,
                "completion_pct": 0,
                "schedule_status": None,
            },
            "projects": [],
            "monthly_breakdown": [],
        }

    nodes_query = db.query(models.WbsNode).filter(
        engineer_wbs_condition(employee_id),
        models.WbsNode.project_id.in_(approved_ids),
    )
    if project_id:
        nodes_query = nodes_query.filter(models.WbsNode.project_id == project_id)
    nodes = nodes_query.all()

    project_ids = {node.project_id for node in nodes}
    projects = db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()
    project_by_id = {project.id: project for project in projects}

    # Get all time entries for this engineer across their projects. Everything the
    # dashboard shows is recomputed from these live rows on every request, so the
    # numbers can never be a cached or stale snapshot.
    entries_query = db.query(models.TimeLogEntry).filter(
        models.TimeLogEntry.employee_id == employee_id,
        models.TimeLogEntry.project_id.in_(approved_ids),
    )
    if project_id:
        entries_query = entries_query.filter(models.TimeLogEntry.project_id == project_id)
    entries = entries_query.all()

    # Resolve the REAL approval state of each entry. The engineer's approval
    # workflow is week-level: a Lead approves a week on Timeline & Logs, which is
    # recorded on WeeklyHoursSubmission. An individual TimeLogEntry is therefore
    # approved either because the entry itself was approved, or because its week
    # was approved. This is read-only dashboard logic, so the Lead/BU Head
    # approval screens keep their own behaviour untouched.
    submission_status_by_week = {
        (row.project_id, row.week_start_date): row.status
        for row in db.query(models.WeeklyHoursSubmission)
        .filter(
            models.WeeklyHoursSubmission.employee_id == employee_id,
            models.WeeklyHoursSubmission.project_id.in_(approved_ids),
        )
        .all()
    }

    def _effective_status(entry) -> str:
        week_status = submission_status_by_week.get((entry.project_id, entry.week_start_date))
        if entry.approval_status == "approved":
            return "approved"
        if week_status == "approved":
            return "approved"
        if week_status == "rejected":
            return "rejected"
        return entry.approval_status or "pending_review"

    approved_entries = [entry for entry in entries if _effective_status(entry) == "approved"]
    pending_entries = [entry for entry in entries if _effective_status(entry) == "pending_review"]

    # Aggregate by project
    per_project = {}
    for project_id in project_ids:
        project = project_by_id.get(project_id)
        per_project[project_id] = {
            "id": project_id,
            "project_name": project.project_name if project else f"Project #{project_id}",
            "project_code": project.project_code if project else "",
            "client_organization": project.client_organization if project else "",
            "project_lead": project.project_lead if project else "",
            "contract_value": float(project.contract_value or 0) if project else 0,
            "contract_currency": project.contract_currency if project else "USD",
            "governance_threshold_pct": float(project.governance_threshold_pct) if project and project.governance_threshold_pct else None,
            "scheduled_hours": 0,
            "logged_hours": 0.0,
            "approved_hours": 0.0,
            "pending_hours": 0.0,
            "total_tasks": 0,
            "started_tasks": 0,
            "completed_tasks": 0,
        }

    # A node counts as STARTED once it has a real actual start timestamp (stamped
    # by the advance-status flow on the first "In-Progress" transition) OR its
    # current status is past "To Do" in the flow. It counts as COMPLETED once a
    # task is "Approved" or a subtask is "Done" (app/domain/wbs.py).
    def _is_started(node):
        return bool(node.actual_start_datetime) or node.deliverable_status != TO_DO

    def _is_completed(node):
        return is_finished(node.deliverable_status)

    for node in nodes:
        row = per_project.get(node.project_id)
        if row:
            row["scheduled_hours"] += node.estimated_hours or 0
            row["total_tasks"] += 1
            if _is_started(node):
                row["started_tasks"] += 1
            if _is_completed(node):
                row["completed_tasks"] += 1

    for entry in approved_entries:
        row = per_project.get(entry.project_id)
        if not row:
            continue
        total = time_entry_total(entry)
        row["approved_hours"] = round(row["approved_hours"] + total, 2)

    for entry in pending_entries:
        row = per_project.get(entry.project_id)
        if not row:
            continue
        total = time_entry_total(entry)
        row["pending_hours"] = round(row["pending_hours"] + total, 2)

    for row in per_project.values():
        row["logged_hours"] = round(row["approved_hours"] + row["pending_hours"], 2)

    # Compute per-project governance threshold status for the engineer from ALL
    # LOGGED consumption against the project's real configured threshold, so a
    # time log the engineer just saved is reflected immediately.
    for project_id in project_ids:
        row = per_project[project_id]
        threshold = row["governance_threshold_pct"]
        scheduled = row["scheduled_hours"]
        consumed = row["logged_hours"]
        pct = round((consumed / scheduled) * 100, 1) if scheduled else 0.0
        row["consumption_pct"] = pct
        row["exceeded"] = threshold is not None and scheduled > 0 and pct > threshold

    # Monthly breakdown: planned baseline, normal consumption, exceeded threshold
    monthly_planned = defaultdict(float)
    monthly_consumed_normal = defaultdict(float)
    monthly_consumed_exceeded = defaultdict(float)

    # Distribute planned baseline hours across months based on WBS node dates
    for node in nodes:
        if node.estimated_hours and node.estimated_hours > 0:
            start = node.start_date
            end = node.target_due_date or node.end_date
            distributed = _distribute_hours_over_months(float(node.estimated_hours), start, end)
            for month_key, hours in distributed.items():
                monthly_planned[month_key] += hours

    # Aggregate APPROVED consumed hours into the REAL month each logged day falls
    # in, splitting normal vs exceeded per project. Bucketing per day (rather than
    # per week start) is what keeps a month correct when a single week straddles a
    # month boundary.
    for entry in approved_entries:
        for month_key, hours in time_entry_hours_by_month(entry).items():
            project_row = per_project.get(entry.project_id)
            if project_row and project_row.get("exceeded"):
                monthly_consumed_exceeded[month_key] += hours
            else:
                monthly_consumed_normal[month_key] += hours

    # Collect all months that have data and sort them
    all_months = sorted(set(monthly_planned.keys()) | set(monthly_consumed_normal.keys()) | set(monthly_consumed_exceeded.keys()))

    monthly_breakdown = []
    for month_key in all_months:
        planned = round(monthly_planned.get(month_key, 0.0), 1)
        # Consumed hours keep 2 decimals so the bars always reconcile exactly
        # with the headline approved total instead of hiding sub-0.05h amounts.
        normal = round(monthly_consumed_normal.get(month_key, 0.0), 2)
        exceeded = round(monthly_consumed_exceeded.get(month_key, 0.0), 2)
        try:
            year, month = map(int, month_key.split("-"))
            month_label = date(year, month, 1).strftime("%b %Y")
        except Exception:
            month_label = month_key
        monthly_breakdown.append({
            "month": month_key,
            "month_label": month_label,
            "planned_baseline": planned,
            "normal_consumption": normal,
            "exceeded_threshold": exceeded,
        })

    # Compute totals across all projects. "Total Hours Consumption" and the
    # monthly bars report APPROVED hours only, so the headline figure is always
    # the real sum of approved daily logs. The governance threshold deliberately
    # keeps its existing approved+pending basis (the same rule the executive
    # dashboard uses), reported separately as governance_consumption_pct.
    total_scheduled = sum(p["scheduled_hours"] for p in per_project.values())
    total_approved = sum(p["approved_hours"] for p in per_project.values())
    total_pending = sum(p["pending_hours"] for p in per_project.values())
    total_logged = sum(p["logged_hours"] for p in per_project.values())

    consumption_pct = round((total_approved / total_scheduled) * 100, 1) if total_scheduled else 0.0
    governance_consumption_pct = round((total_logged / total_scheduled) * 100, 1) if total_scheduled else 0.0

    # Governance threshold status (use max threshold across projects, or first project's threshold)
    thresholds = [p["governance_threshold_pct"] for p in per_project.values() if p["governance_threshold_pct"] is not None]
    governance_threshold = max(thresholds) if thresholds else None
    governance_exceeded = governance_threshold is not None and governance_consumption_pct > governance_threshold
    governance_status = "exceeded" if governance_exceeded else "normal"

    # SPI = approved_hours / scheduled_hours
    spi_value = round(total_approved / total_scheduled, 2) if total_scheduled else None
    if not total_scheduled:
        spi_note = "No baseline planned hours for assigned tasks yet."
    elif spi_value >= 1.0:
        spi_note = f"Earned hours ({total_approved:g}) match or exceed the planned baseline ({total_scheduled:g})."
    else:
        spi_note = f"Behind plan — {total_approved:g} earned of {total_scheduled:g} planned baseline hours."

    # Schedule health from REAL start timestamps vs planned start dates. For every
    # assigned node the engineer has actually started (real actual_start_datetime)
    # with a planned start date, compare the two: started on/before plan is on
    # schedule, started after is behind. No timestamps recorded yet -> no verdict.
    started_nodes = [node for node in nodes if node.actual_start_datetime]
    planned_started = [node for node in started_nodes if node.start_date]
    if planned_started:
        late_starts = [node for node in planned_started if node.actual_start_datetime.date() > node.start_date]
        early_starts = [node for node in planned_started if node.actual_start_datetime.date() < node.start_date]
        if late_starts:
            schedule_status = "behind"
        elif early_starts and len(early_starts) == len(planned_started):
            schedule_status = "ahead"
        else:
            schedule_status = "on schedule"
    else:
        schedule_status = None

    if started_nodes:
        if schedule_status == "behind":
            late_descriptions = [
                f"{node.task_name or node.wbs_code or 'task'} started {node.actual_start_datetime.date()} vs planned {node.start_date}"
                for node in late_starts[:3]
            ]
            spi_note += (
                " Started after the planned start (" + "; ".join(late_descriptions) + ") — behind schedule."
            )
        elif schedule_status == "ahead":
            spi_note += " Started before the planned start — ahead of schedule."
        elif schedule_status == "on schedule":
            spi_note += " Started on or before the planned start — on schedule."
        else:
            spi_note += f" {len(started_nodes)} started task(s) with no planned start date recorded."

    # Task-level progress counts derived purely from real node statuses.
    total_tasks = sum(p["total_tasks"] for p in per_project.values())
    total_started = sum(p["started_tasks"] for p in per_project.values())
    total_completed = sum(p["completed_tasks"] for p in per_project.values())
    completion_pct = round((total_completed / total_tasks) * 100) if total_tasks else 0

    # Convert projects to list
    projects_list = list(per_project.values())

    return {
        "summary": {
            "total_hours_consumption": round(total_approved, 2),
            "total_hours_scheduled": total_scheduled,
            "total_hours_approved": round(total_approved, 2),
            "total_hours_pending": round(total_pending, 2),
            "consumption_pct": consumption_pct,
            "governance_consumption_pct": governance_consumption_pct,
            "governance_status": governance_status,
            "governance_threshold_pct": governance_threshold,
            "governance_exceeded": governance_exceeded,
            "spi_value": spi_value,
            "spi_note": spi_note,
            "total_tasks": total_tasks,
            "started_tasks": total_started,
            "completed_tasks": total_completed,
            "completion_pct": completion_pct,
            "schedule_status": schedule_status,
        },
        "projects": projects_list,
        "monthly_breakdown": monthly_breakdown,
    }


@app.get("/api/engineer-performance-dashboard", response_model=schemas.EngineerDashboardOut)
def engineer_performance_dashboard(
    project_id: int | None = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, STAFF)  # own work: the employee link below is the real gate
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    employee = db.query(models.Employee).filter_by(id=user.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found for this account.")

    approved = visible_project_ids(db, user)
    if project_id is not None and project_id not in approved:
        raise HTTPException(status_code=403, detail="This engineer is not assigned to the requested project.")

    return engineer_dashboard_data(db, user.employee_id, approved, project_id=project_id)


@app.post("/api/projects/{project_id}/extension-requests", response_model=schemas.ExtensionRequestOut, status_code=201)
def create_extension_request_endpoint(
    project_id: int,
    payload: schemas.ExtensionRequestCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, _ = project_and_role(db, project_id, user, allowed={"lead"})
    request = create_extension_request(
        db,
        project,
        user,
        payload.requested_hours,
        payload.justification,
    )
    return extension_request_output(db, request)


@app.post("/api/projects/{project_id}/governance/request-extension", response_model=schemas.GovernanceActionOut)
def request_extension(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, _ = project_and_role(db, project_id, user, allowed={"lead"})
    requested_hours = parse_legacy_requested_hours(payload.comments)
    request = create_extension_request(db, project, user, requested_hours, payload.comments)
    action = (
        db.query(models.GovernanceAction)
        .filter_by(extension_request_id=request.id, action="extension_request")
        .order_by(models.GovernanceAction.id.desc())
        .first()
    )
    return action


def lead_review_time_log(db: Session, entry_id: int, user: models.User, status: str):
    if not user.full_name:
        raise HTTPException(status_code=400, detail="Lead identity is required.")
    entry = db.query(models.TimeLogEntry).filter_by(id=entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Time log entry not found.")
    require_hours_reviewer(db, user, entry.project_id, entry.employee_id)
    task = db.query(models.WbsNode).filter_by(id=entry.task_id).first()
    if not task or (user.role != "bu_head" and not node_assigned_to_lead(task, user)):
        raise HTTPException(status_code=403, detail="This time log is outside your lead scope.")
    project = db.query(models.Project).filter_by(id=entry.project_id).first()
    if project and project.timesheets_soft_locked:
        raise HTTPException(
            status_code=409,
            detail="Timesheets are soft-locked by the BU Head — approvals are on hold.",
        )
    entry.approval_status = status
    entry.reviewed_by = user.full_name
    entry.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    enforce_governance(db, entry.project_id)  # usage = approved hours: alerts / auto-lock
    db.refresh(entry)
    return time_entry_output(db, entry)


@app.post("/api/time-log-entries/{entry_id}/approve")
def approve_time_log(
    entry_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return lead_review_time_log(db, entry_id, user, "approved")


@app.post("/api/time-log-entries/{entry_id}/reject")
def reject_time_log(
    entry_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return lead_review_time_log(db, entry_id, user, "rejected")


# --- Automatic subtask working-time tracking ---------------------------------

SUBTASK_MIN_HOURS = 1
SUBTASK_MAX_HOURS = 4


def validate_subtask_rules(estimated_hours, start_date, end_date):
    """Enforce the subtask working-time rules that underpin automatic
    tracking: planned hours are required and must be 1-4 whole hours, and a
    subtask is a single-day unit whose Start and End dates must be identical.

    Only values explicitly present on the payload are checked, so subtasks
    that inherit dates from their parent main task keep working.
    """
    if estimated_hours is None or not (SUBTASK_MIN_HOURS <= estimated_hours <= SUBTASK_MAX_HOURS):
        raise HTTPException(
            status_code=400,
            detail=f"Subtask planned hours must be between {SUBTASK_MIN_HOURS} and {SUBTASK_MAX_HOURS} hours.",
        )
    if start_date is not None and end_date is not None and start_date != end_date:
        raise HTTPException(
            status_code=400,
            detail="A subtask must be completed within a single working day — Start Date and End Date must be identical.",
        )


def cascade_phase(db: Session, parent_id: int, phase: str):
    for child in db.query(models.WbsNode).filter_by(parent_id=parent_id).all():
        if child.phase != phase:
            child.phase = phase
        cascade_phase(db, child.id, phase)


def estimated_hours_from_dates(start_date, end_date):
    """Derive estimated hours from a Start/End date range, server-side.

    Only weekdays (Monday–Friday) count — both endpoints inclusive — at
    8 hours/day; Saturdays and Sundays are NOT working days. Computing on
    the server keeps the stored value authoritative and consistent with the
    Add WBS Node form: a client-supplied hours value is never trusted when
    both dates are present.

    Returns None when a full range is not available or the range is
    reversed, so callers fall back to the value sent by the client
    (e.g. legacy nodes with hours but no dates). A valid range whose days
    all fall on a weekend yields 0 hours.
    """
    if start_date is None or end_date is None:
        return None
    if end_date < start_date:
        return None
    weekdays = 0
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            weekdays += 1
        cursor += timedelta(days=1)
    return weekdays * 8


@app.post("/api/projects/{project_id}/wbs-nodes", response_model=schemas.WbsNodeOut, status_code=201)
def create_wbs_node(
    project_id: int,
    payload: schemas.WbsNodeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_and_role(db, project_id, user, allowed={"lead"})
    validate_node_payload(db, project_id, payload)
    if payload.wbs_code and db.query(models.WbsNode).filter_by(project_id=project_id, wbs_code=payload.wbs_code).first():
        raise HTTPException(status_code=409, detail="WBS code already exists in this project.")
    phase = payload.phase
    if payload.parent_id is not None:
        parent = db.query(models.WbsNode).filter_by(id=payload.parent_id, project_id=project_id).first()
        phase = parent.phase if parent and parent.phase else phase
    if not phase:
        raise HTTPException(status_code=422, detail="Phase is required. Choose one of the five fixed phases.")
    node_data = payload.model_dump(exclude={"subtask"})
    derived = estimated_hours_from_dates(node_data.get("start_date"), node_data.get("end_date"))
    if derived is not None:
        node_data["estimated_hours"] = derived
    if not node_data.get("assigned_lead_user_id") and not node_data.get("assigned_lead"):
        node_data["assigned_lead"] = user.full_name
        node_data["assigned_lead_user_id"] = user.id
    node_data["phase"] = phase
    node = models.WbsNode(project_id=project_id, **node_data)
    db.add(node)
    db.commit()
    db.refresh(node)
    if payload.subtask and payload.subtask.strip() and node.parent_id is None:
        child_code = None
        if node.wbs_code:
            sibling_count = db.query(models.WbsNode).filter_by(project_id=project_id, parent_id=node.id).count()
            child_code = f"{node.wbs_code.rstrip('.')}.{sibling_count + 1}"
        child = models.WbsNode(
            project_id=project_id,
            parent_id=node.id,
            wbs_code=child_code,
            task_name=payload.subtask.strip(),
            assigned_lead=node.assigned_lead,
            assigned_lead_user_id=node.assigned_lead_user_id,
            estimated_hours=None,
            deliverable_status=TO_DO,
            start_date=node.start_date,
            target_due_date=node.target_due_date,
            end_date=node.end_date,
            phase=node.phase,
        )
        db.add(child)
        db.commit()
    return node_output(db, node)


@app.post("/api/wbs-nodes/{node_id}/subtasks", response_model=schemas.WbsNodeOut, status_code=201)
def create_wbs_subtask(
    node_id: int,
    payload: schemas.WbsNodeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a subtask under an existing WBS node.

    Both the assigned Lead (project scope) and the Engineer assigned to the
    parent node can create subtasks. Visibility is inherited from the parent
    (assigned lead + assigned engineer), so an Engineer-created subtask shows
    up in the Lead's and BU Head's WBS views immediately, and vice versa.
    """
    parent = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent WBS node not found.")
    project = db.query(models.Project).filter_by(id=parent.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    role = project_role(db, user, project.id)
    if role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        if not node_assigned_to_engineer(parent, user):
            raise HTTPException(
                status_code=403,
                detail="You can only create subtasks under WBS nodes assigned to you.",
            )
    elif role is None:
        raise HTTPException(status_code=403, detail="You do not have access to this project.")
    elif role != "lead":
        raise HTTPException(status_code=403, detail="This action is not allowed for the current role.")

    if parent.parent_id is not None:
        raise HTTPException(
            status_code=400,
            detail="A subtask cannot have its own subtasks. Only main tasks can have subtasks.",
        )

    if payload.assigned_engineer_id is not None and not db.query(models.Employee).filter_by(
        id=payload.assigned_engineer_id
    ).first():
        raise HTTPException(status_code=400, detail="Engineer not found.")

    if role == "engineer":
        if payload.assigned_engineer_id is not None and payload.assigned_engineer_id != user.employee_id:
            raise HTTPException(
                status_code=403,
                detail="Only the Lead can assign engineers to a task — you can only plan your own subtasks.",
            )
        validate_subtask_rules(payload.estimated_hours, payload.start_date, payload.end_date)

    if role == "lead":
        validate_subtask_rules(payload.estimated_hours, payload.start_date, payload.end_date)

    phase = payload.phase or parent.phase or "Space Planning"
    sibling_count = db.query(models.WbsNode).filter_by(project_id=parent.project_id, parent_id=parent.id).count()
    child_code = None
    if parent.wbs_code:
        child_code = f"{str(parent.wbs_code).rstrip('.')}.{sibling_count + 1}"
    elif payload.wbs_code:
        child_code = str(payload.wbs_code).strip() or None
    if child_code and db.query(models.WbsNode).filter_by(project_id=parent.project_id, wbs_code=child_code).first():
        raise HTTPException(status_code=409, detail="WBS code already exists in this project.")

    child = models.WbsNode(
        project_id=parent.project_id,
        parent_id=parent.id,
        wbs_code=child_code,
        task_name=payload.task_name.strip(),
        assigned_lead=parent.assigned_lead or (user.full_name if role == "lead" else None),
        assigned_lead_user_id=parent.assigned_lead_user_id or (user.id if role == "lead" else None),
        assigned_engineer_id=payload.assigned_engineer_id
        if payload.assigned_engineer_id is not None
        else parent.assigned_engineer_id,
        estimated_hours=payload.estimated_hours,
        deliverable_status="To Do",
        start_date=payload.start_date if payload.start_date else parent.start_date,
        target_due_date=payload.target_due_date if payload.target_due_date else parent.target_due_date,
        end_date=payload.end_date if payload.end_date else parent.end_date,
        phase=phase,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return node_output(db, child)


@app.put("/api/wbs-nodes/{node_id}", response_model=schemas.WbsNodeOut)
def update_wbs_node(
    node_id: int,
    payload: schemas.WbsNodeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    project_and_role(db, node.project_id, user, allowed={"lead"})
    validate_node_payload(db, node.project_id, payload)
    duplicate = None
    if payload.wbs_code:
        duplicate = db.query(models.WbsNode).filter(models.WbsNode.project_id == node.project_id, models.WbsNode.wbs_code == payload.wbs_code, models.WbsNode.id != node_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="WBS code already exists in this project.")
    for field, value in payload.model_dump(exclude={"subtask", "phase", "parent_id"}).items():
        setattr(node, field, value)
    if node.parent_id is not None:
        merged_hours = payload.estimated_hours if payload.estimated_hours is not None else node.estimated_hours
        merged_start = payload.start_date if payload.start_date is not None else node.start_date
        merged_end = payload.end_date if payload.end_date is not None else node.end_date
        validate_subtask_rules(merged_hours, merged_start, merged_end)
    else:
        derived = estimated_hours_from_dates(payload.start_date, payload.end_date)
        if derived is not None:
            node.estimated_hours = derived
    if node.assigned_lead_user_id is None and node.assigned_lead is None:
        node.assigned_lead = user.full_name
        node.assigned_lead_user_id = user.id
    phase_changed = payload.phase is not None and payload.phase != node.phase
    if payload.phase is not None:
        node.phase = payload.phase
    db.commit()
    if phase_changed:
        cascade_phase(db, node.id, node.phase)
        db.commit()
    db.refresh(node)
    return node_output(db, node)


@app.delete("/api/wbs-nodes/{node_id}")
def delete_wbs_node(
    node_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    project_and_role(db, node.project_id, user, allowed={"lead"})
    descendant_ids = []
    stack = [node_id]
    while stack:
        current = stack.pop()
        descendant_ids.append(current)
        children = db.query(models.WbsNode.id).filter_by(parent_id=current).all()
        stack.extend(cid for (cid,) in children)
    db.query(models.WbsNodeHistory).filter(
        models.WbsNodeHistory.node_id.in_(descendant_ids)
    ).delete(synchronize_session=False)
    db.query(models.TimeLogEntry).filter(
        models.TimeLogEntry.task_id.in_(descendant_ids)
    ).delete(synchronize_session=False)
    db.query(models.TimeSession).filter(
        models.TimeSession.subtask_id.in_(descendant_ids) | models.TimeSession.task_id.in_(descendant_ids)
    ).delete(synchronize_session=False)
    db.query(models.WbsNode).filter(
        models.WbsNode.id.in_(descendant_ids)
    ).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted_nodes": descendant_ids}


_FIELD_ALIASES = {
    "wbs_code": {"wbs_code", "code", "wbs", "wbs_no", "task_code", "task_no"},
    "task_name": {"task_name", "task", "name", "taskname", "activity", "description", "deliverable"},
    "parent_wbs_code": {"parent_wbs_code", "parent_code", "parent", "parent_wbs"},
    "assigned_lead": {"assigned_lead", "lead", "lead_name", "leadname", "lead_wbs"},
    "assigned_engineer": {"assigned_engineer", "engineer", "engineer_name", "assigned_engineer_name", "responsible_engineer"},
    "assigned_engineer_id": {"assigned_engineer_id", "engineer_id", "engineer_no"},
    "estimated_hours": {"estimated_hours", "hours", "planned_hours", "hours_planned", "duration"},
    "deliverable_status": {"deliverable_status", "status", "deliverable", "wbs_status", "task_status"},
    "target_due_date": {"target_due_date", "due_date", "target", "due", "target_date"},
    "phase": {"phase", "wbs_phase", "phase_name", "wbs_phase_category"},
}


def _header_field(value):
    token = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if not token:
        return None
    for field, aliases in _FIELD_ALIASES.items():
        if token in aliases or token.startswith(field + "_") or token == field:
            return field
    return None


def _parse_xlsx_rows(content):
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        shared = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in shared_root.findall("main:si", namespace)]
        sheet_name = "xl/worksheets/sheet1.xml"
        sheet_root = ElementTree.fromstring(workbook.read(sheet_name))
        raw = []
        for row in sheet_root.findall(".//main:row", namespace):
            row_num = int(row.get("r") or 0)
            cells = {}
            for cell in row.findall("main:c", namespace):
                ref = cell.get("r") or ""
                letter = "".join(ch for ch in ref if ch.isalpha()).upper()
                value_el = cell.find("main:v", namespace)
                text = value_el.text if value_el is not None else ""
                if cell.get("t") == "s" and text:
                    text = shared[int(text)]
                cells[letter] = text
            raw.append((row_num, cells))
    return raw


def parse_wbs_upload(upload: UploadFile, content: bytes):
    filename = (upload.filename or "").lower()
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        if filename.endswith(".xls"):
            raise HTTPException(status_code=415, detail="Use .xlsx or .csv format for WBS upload.")
        raw_rows = _parse_xlsx_rows(content)
        keyed = True
    else:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")))
        raw_rows = [(reader.line_num, row) for row in reader]
        keyed = False

    if not raw_rows:
        return []

    def cell_item(entry, key):
        cells = entry[1]
        if keyed:
            return cells.get(key, "")
        return cells[key] if key < len(cells) else ""

    def row_nz(entry):
        vals = list(entry[1].values()) if keyed else entry[1]
        return any(str(v).strip() for v in vals)

    # Locate the header row: the first row containing a recognised
    # "WBS Code" / "Task Name" column. Rows above it (title rows, notes)
    # are ignored instead of being misread as the column headers.
    header_index = None
    for i, entry in enumerate(raw_rows):
        fields = {_header_field(v) for v in entry[1].values()} if keyed else {_header_field(v) for v in entry[1]}
        if "wbs_code" in fields or "task_name" in fields:
            header_index = i
            break
    if header_index is None:
        for i, entry in enumerate(raw_rows):
            if row_nz(entry):
                header_index = i
                break
        if header_index is None:
            return []

    header_entry = raw_rows[header_index]
    header_keys = sorted(header_entry[1].keys()) if keyed else list(range(len(header_entry[1])))
    header_map = {key: field for key in header_keys if (field := _header_field(cell_item(header_entry, key)))}
    header_sig = frozenset((field, str(cell_item(header_entry, key)).strip()) for key, field in sorted(header_map.items()))

    parsed = []
    for i, entry in enumerate(raw_rows):
        if i <= header_index:
            continue
        if not row_nz(entry):
            continue  # blank / spacer row
        row_sig = frozenset((field, str(cell_item(entry, key)).strip()) for key, field in sorted(header_map.items()))
        if row_sig == header_sig:
            continue  # repeated header row
        row_dict = {field: cell_item(entry, key) for key, field in header_map.items()}
        # Summary rows (e.g. "Total" in the WBS Code column) are noise, not data
        # errors - skip them instead of failing with "missing Task Name".
        code_val = str(row_dict.get("wbs_code") or "").strip().lower()
        if code_val in {"total", "totals", "subtotal", "grand total", "grand subtotal", "total hours"}:
            continue
        row_num = entry[0] or (i + 1)
        parsed.append((row_num, row_dict))
    return parsed


@app.post("/api/projects/{project_id}/wbs-upload")
async def upload_wbs(
    project_id: int,
    file: UploadFile = File(...),
    phase: Optional[str] = Form(None),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project, _ = project_and_role(db, project_id, user, allowed={"lead"})
    requested_phase = phase.strip() if phase and phase.strip() else None
    if requested_phase and requested_phase not in schemas.WBS_PHASES:
        raise HTTPException(status_code=422, detail=f"Phase '{requested_phase}' is not one of the five fixed phases.")
    rows = parse_wbs_upload(file, await file.read())
    if not rows:
        raise HTTPException(status_code=400, detail="The WBS file contains no rows.")
    created = updated = 0
    code_to_id = {node.wbs_code: node.id for node in db.query(models.WbsNode).filter_by(project_id=project_id).all()}
    employees = db.query(models.Employee).all()
    engineer_by_name = {e.name.strip().lower(): e.id for e in employees}
    # Highest numeric root currently in use (e.g. "100." / "1") so we can mint
    # unique codes for rows uploaded without a WBS Code.
    used_roots = set()
    for c in code_to_id:
        m = re.match(r"(\d+)", str(c))
        if m:
            used_roots.add(int(m.group(1)))
    next_root = (max(used_roots) + 1) if used_roots else 1
    invalid = []
    for row_num, row in rows:
        normalized = {str(key).strip().lower().replace(" ", "_"): value for key, value in row.items()}
        task_name = str(normalized.get("task_name") or normalized.get("task") or normalized.get("name") or "").strip()
        if not task_name:
            parsed = {k: v for k, v in normalized.items() if k in ("wbs_code", "task_name", "parent_wbs_code", "assigned_lead", "assigned_engineer", "estimated_hours", "deliverable_status", "target_due_date", "phase")}
            invalid.append((row_num, "Task Name", parsed))
            continue
        raw_code = str(normalized.get("wbs_code") or normalized.get("code") or "").strip()
        if raw_code:
            code = raw_code
        else:
            while f"{next_root}." in code_to_id:
                next_root += 1
            code = f"{next_root}."
            next_root += 1
        due = normalized.get("target_due_date") or normalized.get("due_date") or None
        parent_code = str(normalized.get("parent_wbs_code") or normalized.get("parent_code") or "").strip()
        parent_id = int(normalized["parent_id"]) if normalized.get("parent_id") else code_to_id.get(parent_code)
        phase_raw = str(normalized.get("phase") or "").strip()
        if requested_phase:
            phase = requested_phase
        else:
            phase = phase_raw if phase_raw in schemas.WBS_PHASES else "Space Planning"
            if phase_raw and phase_raw not in schemas.WBS_PHASES:
                raise HTTPException(status_code=422, detail=f"Phase '{phase_raw}' is not one of the five fixed phases.")
        engineer_id = None
        if normalized.get("assigned_engineer_id"):
            engineer_id = int(normalized["assigned_engineer_id"])
        elif normalized.get("assigned_engineer"):
            name = str(normalized["assigned_engineer"]).strip()
            engineer_id = engineer_by_name.get(name.lower())
            if engineer_id is None:
                parsed = {k: v for k, v in normalized.items() if k in ("wbs_code", "task_name", "parent_wbs_code", "assigned_lead", "assigned_engineer", "estimated_hours", "deliverable_status", "target_due_date", "phase")}
                invalid.append((row_num, f"Assigned Engineer '{name}' not found", parsed))
                continue
        payload = schemas.WbsNodeUpdate(
            wbs_code=code,
            task_name=task_name,
            parent_id=parent_id,
            assigned_lead=normalized.get("assigned_lead") or user.full_name,
            assigned_lead_user_id=user.id,
            assigned_engineer_id=engineer_id,
            estimated_hours=int(float(normalized.get("estimated_hours") or normalized.get("planned_hours") or 0)),
            deliverable_status=normalized.get("deliverable_status") or normalized.get("status") or TO_DO,
            target_due_date=due,
            phase=phase,
        )
        validate_node_payload(db, project_id, payload)
        node = db.query(models.WbsNode).filter_by(project_id=project_id, wbs_code=code).first()
        if node:
            updated_phase = node.phase != phase
            for field, value in payload.model_dump(exclude={"subtask"}).items():
                setattr(node, field, value)
            db.commit()
            if updated_phase:
                cascade_phase(db, node.id, phase)
                db.commit()
            updated += 1
        else:
            db.add(models.WbsNode(project_id=project_id, **payload.model_dump(exclude={"subtask"})))
            db.commit()
            created += 1
        saved_node = db.query(models.WbsNode).filter_by(project_id=project_id, wbs_code=code).first()
        code_to_id[code] = saved_node.id
    if invalid:
        print(f"[wbs-upload] REJECTED {len(invalid)} of {len(rows)} rows (project {project_id}):", flush=True)
        for row_num, reason, parsed in invalid:
            print(f"  - Excel row {row_num}: {reason}; parsed values: {parsed}", flush=True)
        detail = "Upload rejected. " + "; ".join(
            f"Row {row_num}: {reason} (parsed: {parsed})" for row_num, reason, parsed in invalid
        )
        raise HTTPException(status_code=422, detail=detail)
    return {"created": created, "updated": updated, "phase": requested_phase or None}


def map_status_for_display(status: str) -> str:
    """Map legacy status values to current flow names."""
    status_map = {
        "Not Started": "To Do",
        "In Progress": "In-Progress",
        "Blocked": "To Do",
    }
    return status_map.get(status, status)


def get_node_detail(db: Session, node_id: int, user: models.User):
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    role = project_role(db, user, node.project_id)
    if role is None and user.role != "bu_head":
        raise HTTPException(status_code=403, detail="You do not have access to this project.")
    if role == "engineer" or (role == "lead" and node_assigned_to_engineer(node, user)):
        if not node_assigned_to_engineer(node, user):
            raise HTTPException(status_code=403, detail="You can only view tasks assigned to you.")
    elif role == "lead":
        if node.assigned_lead and node.assigned_lead != user.full_name:
            has_scope = False
            if node.assigned_engineer_id:
                eng = db.query(models.Employee).filter_by(id=node.assigned_engineer_id).first()
                if eng and eng.name == user.full_name:
                    has_scope = True
            if not has_scope:
                raise HTTPException(status_code=403, detail="You can only view tasks assigned under your scope.")
    elif role != "bu_head":
        raise HTTPException(status_code=403, detail="Insufficient permissions.")

    history = (
        db.query(models.WbsNodeHistory)
        .filter_by(node_id=node_id)
        .order_by(models.WbsNodeHistory.created_at.desc())
        .all()
    )
    parent_node = None
    if node.parent_id:
        parent_node = db.query(models.WbsNode).filter_by(id=node.parent_id).first()

    linked_code = parent_node.wbs_code if parent_node else None
    linked_task_name = parent_node.task_name if parent_node else None
    ntype = "subtask" if node.parent_id else "task"
    display_status = map_status_for_display(node.deliverable_status)

    children_out = [
        {
            "id": child.id,
            "project_id": child.project_id,
            "parent_id": child.parent_id,
            "wbs_code": child.wbs_code,
            "task_name": child.task_name,
            "deliverable_status": map_status_for_display(child.deliverable_status),
        }
        for child in db.query(models.WbsNode)
        .filter_by(parent_id=node_id)
        .order_by(models.WbsNode.wbs_code, models.WbsNode.id)
        .all()
    ]

    return schemas.WbsNodeDetailOut(
        id=node.id,
        project_id=node.project_id,
        parent_id=node.parent_id,
        wbs_code=node.wbs_code,
        task_name=node.task_name,
        assigned_lead=node.assigned_lead,
        assigned_engineer_id=node.assigned_engineer_id,
        assigned_engineer_name=db.query(models.Employee).filter_by(id=node.assigned_engineer_id).first().name if node.assigned_engineer_id else None,
        estimated_hours=node.estimated_hours,
        deliverable_status=display_status,
        start_date=node.start_date,
        target_due_date=node.target_due_date,
        end_date=node.end_date,
        phase=node.phase,
        level=node_level(db, node),
        description=node.description,
        severity=node.severity,
        actual_start_datetime=node.actual_start_datetime.isoformat() if node.actual_start_datetime else None,
        actual_end_datetime=node.actual_end_datetime.isoformat() if node.actual_end_datetime else None,
        node_type=ntype,
        linked_code=linked_code,
        linked_task_name=linked_task_name,
        history=[schemas.WbsNodeHistoryOut.model_validate(h) for h in history],
        children=children_out,
    )


@app.get("/api/wbs-nodes/{node_id}", response_model=schemas.WbsNodeDetailOut)
def get_wbs_node_detail(
    node_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_node_detail(db, node_id, user)


@app.post("/api/wbs-nodes/{node_id}/advance-status")
def advance_wbs_node_status(
    node_id: int,
    payload: schemas.WbsNodeStatusUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    is_subtask = node.parent_id is not None
    project = db.query(models.Project).filter_by(id=node.project_id).first()

    # Who may advance a node:
    #  - Engineer: any WBS node assigned to them (tasks and subtasks).
    #  - Lead: subtasks only (the engineer drives task statuses; the Lead
    #    approves submitted tasks via the dedicated /approve action).
    #  - BU Head: never.
    role = project_role(db, user, node.project_id)
    if node_assigned_to_engineer(node, user):
        pass  # the person doing the work (an engineer, or a lead on their own subtask)
    elif role == "engineer":
        raise HTTPException(status_code=403, detail="You can only update tasks assigned to you.")
    elif role == "lead":
        if not node_assigned_to_lead(node, user):
            raise HTTPException(
                status_code=403,
                detail="You can only update subtasks assigned under your WBS scope.",
            )
        if not is_subtask:
            raise HTTPException(
                status_code=403,
                detail="Only engineers advance task statuses. Use the Approve action to approve a submitted task.",
            )
    else:
        raise HTTPException(status_code=403, detail="Only engineers (and leads for subtasks) can advance status.")

    validation_error = validate_status_transition(node.deliverable_status, payload.new_status, node)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    # Re-posting the current status is a no-op (e.g. 'In-Progress' while already
    # awaiting approval, or re-submitting an already submitted task). Reject it
    # instead of silently appending a duplicate history entry.
    if map_status_for_display(node.deliverable_status) == payload.new_status:
        raise HTTPException(status_code=400, detail=f"Task is already '{payload.new_status}'.")

    # A task's 'Approved' step is a Lead-only approval decision — never a
    # status an engineer can advance through on their own.
    if not is_subtask and payload.new_status == "Approved":
        raise HTTPException(
            status_code=403,
            detail="Only the Lead assigned to this task can approve it. Use the Approve action.",
        )

    # Parent task cannot be submitted for approval until ALL subtasks are Done.
    if not is_subtask and payload.new_status == "Submitted for Approval":
        blocking = incomplete_subtasks(db, node)
        if blocking:
            raise HTTPException(status_code=400, detail=subtask_gate_error(blocking))

    old_status = map_status_for_display(node.deliverable_status)
    node.deliverable_status = payload.new_status

    # "Actual Start/End Date and Time" come from the real server clock at the
    # moment this transition is processed — never from the client. A node's
    # flow only moves forward here, but a Lead can still edit a status back
    # via the update endpoint, so each timestamp is set on the FIRST genuine
    # occurrence and preserved (never overwritten) on any later transition.
    if payload.new_status == "In-Progress" and node.actual_start_datetime is None:
        node.actual_start_datetime = datetime.now(timezone.utc)
    if is_subtask and payload.new_status == "Done" and node.actual_end_datetime is None:
        node.actual_end_datetime = datetime.now(timezone.utc)

    history_entry = models.WbsNodeHistory(
        node_id=node_id,
        project_id=node.project_id,
        user_id=user.id,
        user_name=user.full_name or user.username,
        action="status_change",
        old_status=old_status,
        new_status=payload.new_status,
        comment=payload.comment,
    )
    db.add(history_entry)
    db.commit()
    db.refresh(node)

    return {
        "ok": True,
        "node": node_output(db, node),
        "message": f"Status updated to '{payload.new_status}'." + (f" {payload.comment}" if payload.comment else ""),
    }


@app.post("/api/wbs-nodes/{node_id}/approve")
def approve_wbs_node(
    node_id: int,
    payload: schemas.WbsNodeStatusUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lead-only approval of a submitted parent task.

    Moves a Task from 'Submitted for Approval' to 'Approved'. Only the Lead
    assigned to that project/task can approve — BU Head is denied here. The
    BU Head's role in this workflow is governance-level actions on the
    Executive Dashboard, not individual task approval.
    """
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    project_and_role(db, node.project_id, user, allowed={"lead"})
    if node.parent_id:
        raise HTTPException(
            status_code=400,
            detail="Only parent tasks are approved. Subtasks move directly to 'Done'.",
        )
    if not node_assigned_to_lead(node, user):
        raise HTTPException(
            status_code=403,
            detail="Only the Lead assigned to this task can approve it.",
        )

    display_status = map_status_for_display(node.deliverable_status)
    if display_status != "Submitted for Approval":
        raise HTTPException(
            status_code=409,
            detail="This task is not 'Submitted for Approval', so it cannot be approved.",
        )

    blocking = incomplete_subtasks(db, node)
    if blocking:
        raise HTTPException(status_code=400, detail=subtask_gate_error(blocking))

    node.deliverable_status = "Approved"
    if node.actual_end_datetime is None:
        node.actual_end_datetime = datetime.now(timezone.utc)
    history_entry = models.WbsNodeHistory(
        node_id=node_id,
        project_id=node.project_id,
        user_id=user.id,
        user_name=user.full_name or user.username,
        action="status_change",
        old_status="Submitted for Approval",
        new_status="Approved",
        comment=payload.comment,
    )
    db.add(history_entry)
    db.commit()
    db.refresh(node)

    return {
        "ok": True,
        "node": node_output(db, node),
        "message": "Task approved.",
    }


@app.post("/api/wbs-nodes/{node_id}/comments")
def add_wbs_node_comment(
    node_id: int,
    payload: schemas.WbsNodeCommentInput,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "bu_head":
        raise HTTPException(status_code=403, detail="Only engineers can add comments.")
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")

    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    if not node_assigned_to_engineer(node, user):
        raise HTTPException(status_code=403, detail="You can only comment on tasks assigned to you.")

    history_entry = models.WbsNodeHistory(
        node_id=node_id,
        project_id=node.project_id,
        user_id=user.id,
        user_name=user.full_name or user.username,
        action="comment",
        old_status=node.deliverable_status,
        new_status=node.deliverable_status,
        comment=payload.comment,
    )
    db.add(history_entry)
    db.commit()

    return {
        "ok": True,
        "message": "Comment added.",
    }


@app.get("/api/server-date")
def get_server_date():
    """Return the current server date/time for client synchronization."""
    from datetime import datetime
    now = datetime.now(timezone.utc)
    return {
        "date": now.date().isoformat(),
        "datetime": now.isoformat(),
        "timezone": "UTC"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


