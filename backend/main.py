import logging
import os
import csv
import io
import json
import re
import secrets
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from datetime import date, datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
import sharepoint_service
from auth import get_current_user, verify_password
from database import Base, SessionLocal, engine, get_db
from sharepoint_service import get_sharepoint_mirror_data, SharePointError

logger = logging.getLogger(__name__)

# Create tables on startup (fine for dev; use Alembic migrations in production)
Base.metadata.create_all(bind=engine)


def add_missing_wbs_columns():
    inspector = __import__("sqlalchemy").inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("wbs_nodes")}
    with engine.begin() as connection:
        if "start_date" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN start_date DATE")
        if "end_date" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN end_date DATE")


def make_wbs_columns_nullable():
    """Recreate wbs_nodes so wbs_code/estimated_hours accept NULL (SQLite
    cannot ALTER a column's nullability, so we rebuild the table once)."""
    import re
    from sqlalchemy import inspect as _inspect
    inspector = _inspect(engine)
    if "wbs_nodes" not in inspector.get_table_names():
        return
    columns = {column["name"]: column["nullable"] for column in inspector.get_columns("wbs_nodes")}
    if columns.get("wbs_code") is not False and columns.get("estimated_hours") is not False:
        return
    with engine.begin() as connection:
        rows = connection.exec_driver_sql("PRAGMA table_info(wbs_nodes)").fetchall()
        col_defs = []
        for cid, name, ctype, notnull, dflt, pk in rows:
            is_nullable = name in ("wbs_code", "estimated_hours")
            bits = [f'"{name}" {ctype}']
            if notnull == 1 and not is_nullable:
                bits.append("NOT NULL")
            if dflt is not None:
                bits.append(f"DEFAULT {dflt}")
            if pk:
                bits.append("PRIMARY KEY")
            col_defs.append(" ".join(bits))
        names = ", ".join(f'"{row[1]}"' for row in rows)
        connection.exec_driver_sql(
            f"CREATE TABLE wbs_nodes_new ({', '.join(col_defs)})"
        )
        connection.exec_driver_sql(
            f"INSERT INTO wbs_nodes_new ({names}) SELECT {names} FROM wbs_nodes"
        )
        connection.exec_driver_sql("DROP TABLE wbs_nodes")
        connection.exec_driver_sql("ALTER TABLE wbs_nodes_new RENAME TO wbs_nodes")
        connection.exec_driver_sql("CREATE INDEX ix_wbs_nodes_project_id ON wbs_nodes (project_id)")
        connection.exec_driver_sql("CREATE INDEX ix_wbs_nodes_parent_id ON wbs_nodes (parent_id)")
        connection.exec_driver_sql("CREATE INDEX ix_wbs_nodes_wbs_code ON wbs_nodes (wbs_code)")
        connection.exec_driver_sql("CREATE INDEX ix_wbs_nodes_assigned_engineer_id ON wbs_nodes (assigned_engineer_id)")


add_missing_wbs_columns()
make_wbs_columns_nullable()


def add_phase_column():
    """Add the WBS phase grouping column and assign the project's default
    (legacy Excel-upload) mapping to existing nodes that predate phases."""
    inspector = __import__("sqlalchemy").inspect(engine)
    if "wbs_nodes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("wbs_nodes")}
    with engine.begin() as connection:
        if "phase" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN phase VARCHAR(50)")
        connection.exec_driver_sql(
            "UPDATE wbs_nodes SET phase = ? WHERE phase IS NULL",
            ("Space Planning",),
        )


add_phase_column()


def add_governance_columns():
    """Add executive-dashboard / governance metadata to the projects table.

    The governance_actions table itself is created by
    Base.metadata.create_all() since it is a brand-new model.
    """
    inspector = __import__("sqlalchemy").inspect(engine)
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    with engine.begin() as connection:
        if "contract_value" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN contract_value FLOAT DEFAULT 0"
            )
        if "contract_currency" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN contract_currency VARCHAR(10) DEFAULT 'USD'"
            )
        if "governance_threshold_pct" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN governance_threshold_pct FLOAT DEFAULT 80"
            )
        if "timesheets_soft_locked" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN timesheets_soft_locked INTEGER DEFAULT 0"
            )


add_governance_columns()


def add_extension_workflow_columns():
    """Add persisted extension-request state to existing development databases."""
    inspector = __import__("sqlalchemy").inspect(engine)
    if "projects" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("projects")}
        with engine.begin() as connection:
            if "extension_status" not in columns:
                connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN extension_status VARCHAR(20)")
            if "extension_approved_hours" not in columns:
                connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN extension_approved_hours FLOAT")
    if "governance_actions" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("governance_actions")}
        with engine.begin() as connection:
            if "extension_request_id" not in columns:
                connection.exec_driver_sql("ALTER TABLE governance_actions ADD COLUMN extension_request_id INTEGER")
            if "requested_hours" not in columns:
                connection.exec_driver_sql("ALTER TABLE governance_actions ADD COLUMN requested_hours FLOAT")


add_extension_workflow_columns()


def add_project_creation_columns():
    """Add the BU Head 'Create Project' form columns to the existing projects
    table. They back the same Project model (no separate table/model) so the
    JSON payload from CreateProjectPage.jsx can be persisted and re-read via
    GET /api/projects for the 'Created Projects' list."""
    inspector = __import__("sqlalchemy").inspect(engine)
    if "projects" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    with engine.begin() as connection:
        if "project_lead_electrical" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN project_lead_electrical VARCHAR(150)")
        if "project_lead_mechanical" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN project_lead_mechanical VARCHAR(150)")
        if "project_lead_bim" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN project_lead_bim VARCHAR(150)")
        if "sharepoint_disciplines" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN sharepoint_disciplines TEXT")
        if "target_effort_hours" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN target_effort_hours FLOAT")
        if "sharepoint_site_url" not in columns:
            connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN sharepoint_site_url VARCHAR(500)")


add_project_creation_columns()


def add_wbs_detail_columns():
    """Add description, severity, and actual datetime columns to wbs_nodes
    for the Task Details view."""
    inspector = __import__("sqlalchemy").inspect(engine)
    if "wbs_nodes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("wbs_nodes")}
    with engine.begin() as connection:
        if "description" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN description TEXT")
        if "severity" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN severity VARCHAR(20)")
        if "actual_start_datetime" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN actual_start_datetime DATETIME")
        if "actual_end_datetime" not in columns:
            connection.exec_driver_sql("ALTER TABLE wbs_nodes ADD COLUMN actual_end_datetime DATETIME")


add_wbs_detail_columns()


def add_resource_booking_approval_columns():
    """Add the BU Head resource-booking approval workflow columns.

    The resource_bookings table already exists in dev databases, so the
    approval state is added via ALTER TABLE (same pattern as the other
    migrations above). Existing rows default to 'draft'.
    """
    inspector = __import__("sqlalchemy").inspect(engine)
    if "resource_bookings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("resource_bookings")}
    with engine.begin() as connection:
        if "approval_status" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE resource_bookings ADD COLUMN approval_status VARCHAR(20) DEFAULT 'draft'"
            )
        if "submitted_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE resource_bookings ADD COLUMN submitted_at DATETIME")
        if "approved_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE resource_bookings ADD COLUMN approved_at DATETIME")


add_resource_booking_approval_columns()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


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


def require_role(role: Optional[str], allowed: set[str]):
    if role not in allowed:
        raise HTTPException(status_code=403, detail="This action is not allowed for the current role.")


EXTENSION_STATUS_LABELS = {
    "pending": "Pending BU Head Approval",
    "approved": "Approved",
    "rejected": "Rejected",
}


def extension_request_output(db: Session, request: models.ExtensionRequest) -> dict:
    project = db.query(models.Project).filter_by(id=request.project_id).first()
    return {
        "id": request.id,
        "project_id": request.project_id,
        "project_name": project.project_name if project else "",
        "requested_by": request.requested_by,
        "requested_by_user_id": request.requested_by_user_id,
        "requested_hours": request.requested_hours,
        "justification": request.justification,
        "status": request.status,
        "status_label": EXTENSION_STATUS_LABELS.get(request.status, request.status),
        "decision_comments": request.decision_comments,
        "decided_by": request.decided_by,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
    }


def find_pending_extension_request(db: Session, project_id: int) -> Optional[models.ExtensionRequest]:
    return (
        db.query(models.ExtensionRequest)
        .filter_by(project_id=project_id, status="pending")
        .order_by(models.ExtensionRequest.requested_at.desc(), models.ExtensionRequest.id.desc())
        .first()
    )


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
        consumption_pct=data["governance_status"]["max_discipline_pct"],
        threshold_pct=project.governance_threshold_pct,
        consumption_hours=data["summary"]["logged_hours"],
        comments=justification,
        created_by=user.full_name,
        extension_request_id=request.id,
        requested_hours=request.requested_hours,
    )
    project.extension_status = "pending"
    db.add(action)
    db.commit()
    db.refresh(request)
    return request


def decide_extension_request(
    db: Session,
    project: models.Project,
    request: models.ExtensionRequest,
    decision: str,
    comments: Optional[str],
    user: models.User,
) -> models.ExtensionRequest:
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="This extension request has already been decided.")

    status = "approved" if decision == "approve" else "rejected"
    request.status = status
    request.decision_comments = comments
    request.decided_by = user.full_name or user.username
    request.decided_at = datetime.now()
    project.extension_status = status
    if status == "approved":
        project.extension_approved_hours = (project.extension_approved_hours or 0) + request.requested_hours

    data = executive_dashboard_data(db, project)
    action = models.GovernanceAction(
        project_id=project.id,
        action="approve_extension" if status == "approved" else "reject_extension",
        discipline=data["governance_status"]["max_discipline"],
        consumption_pct=data["governance_status"]["max_discipline_pct"],
        threshold_pct=project.governance_threshold_pct,
        consumption_hours=data["summary"]["logged_hours"],
        comments=comments,
        created_by=user.full_name or user.username,
        extension_request_id=request.id,
        requested_hours=request.requested_hours,
    )
    db.add(action)
    db.commit()
    db.refresh(request)
    return request


@app.post("/api/auth/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = secrets.token_hex(32)
    db.add(models.LoginSession(token=token, user_id=user.id))
    db.commit()
    return schemas.LoginResponse(
        token=token,
        role=user.role,
        username=user.username,
        full_name=user.full_name,
        engineer_id=user.employee_id if user.role == "engineer" else None,
    )


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    # Idempotent: deleting a missing/already-deleted session is fine.
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        session = db.query(models.LoginSession).filter_by(token=token).first()
        if session:
            db.delete(session)
            db.commit()
    return {"ok": True}


@app.get("/api/auth/me", response_model=schemas.UserOut)
def auth_me(user: models.User = Depends(get_current_user)):
    return user


def identity(user: models.User) -> dict:
    """Where do lead/engineer scoping values come from? The authenticated user."""
    return {
        "role": user.role,
        "engineer_id": user.employee_id if user.role == "engineer" else None,
        "lead_name": user.full_name if user.role == "lead" else None,
        "full_name": user.full_name or user.username,
    }


def engineer_wbs_condition(employee_id: int, full_name: str | None):
    """SQL condition: WBS node assigned to an engineer by employee id OR by name."""
    conditions = [models.WbsNode.assigned_engineer_id == employee_id]
    if full_name:
        conditions.append(models.WbsNode.assigned_lead == full_name)
    return or_(*conditions)


def engineer_wbs_ids(db: Session, employee_id: int, full_name: str | None) -> set:
    """Projects where the engineer has a WBS node assigned by employee id OR by name."""
    return {
        project_id
        for (project_id,) in db.query(models.WbsNode.project_id)
        .filter(engineer_wbs_condition(employee_id, full_name))
        .distinct()
        .all()
    }


def node_assigned_to_engineer(node: models.WbsNode, user: models.User) -> bool:
    """True if the engineer owns this WBS node by employee id OR by matching full name."""
    if node.assigned_engineer_id == user.employee_id:
        return True
    if user.full_name and node.assigned_lead == user.full_name:
        return True
    return False


def task_output(db: Session, task: models.GanttTask):
    engineer = db.query(models.Employee).filter_by(id=task.assigned_engineer_id).first() if task.assigned_engineer_id else None
    return schemas.WbsTaskOut(
        id=task.id,
        project_id=task.project_id,
        wbs_code=task.wbs_code,
        task_name=task.task_name,
        status=task.status,
        planned_hours=task.planned_hours,
        assigned_engineer_id=task.assigned_engineer_id,
        assigned_engineer_name=engineer.name if engineer else None,
    )


@app.get("/api/project-leads", response_model=List[schemas.ProjectLeadOut])
def list_project_leads(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ProjectLead).order_by(models.ProjectLead.name).all()


@app.post("/api/projects", response_model=schemas.CreateProjectOut, status_code=201)
async def create_project(
    payload: schemas.ProjectCreatePayload,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    # The BU Head 'Create Project' form posts a JSON body. Map its fields onto
    # the existing projects table (same model as GET /api/projects — no
    # duplicate table/model). The single project_lead column keeps the primary
    # (electrical) lead for compatibility with any existing read paths.
    if db.query(models.Project).filter_by(project_code=payload.project_code).first():
        raise HTTPException(status_code=409, detail="Project Code already exists")

    db_project = models.Project(
        project_name=payload.project_name,
        project_code=payload.project_code,
        client_organization=payload.client_customer,
        project_lead=payload.project_lead_electrical,
        start_date=payload.target_start_date,
        project_lead_electrical=payload.project_lead_electrical,
        project_lead_mechanical=payload.project_lead_mechanical,
        project_lead_bim=payload.project_lead_bim,
        sharepoint_disciplines=json.dumps(payload.sharepoint_disciplines) if payload.sharepoint_disciplines else None,
        contract_value=payload.total_contract_value,
        contract_currency=payload.contract_currency,
        governance_threshold_pct=payload.alert_override_threshold_pct,
        target_effort_hours=payload.target_effort_hours,
    )

    try:
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project Code already exists")

    data = schemas.ProjectOut.model_validate(db_project).model_dump()

    # Provision SharePoint directory if disciplines were selected
    if payload.sharepoint_disciplines:
        try:
            sharepoint_url = await sharepoint_service.provision_sharepoint_directory(db_project)
            db_project.sharepoint_site_url = sharepoint_url
            db.commit()
            db.refresh(db_project)
            data["sharepoint_status"] = "provisioned"
            data["sharepoint_site_url"] = sharepoint_url
        except sharepoint_service.SharePointError as e:
            logger.error(f"SharePoint provisioning failed for project {db_project.project_code}: {e}")
            data["sharepoint_status"] = "failed"
            data["sharepoint_site_url"] = None
            data["sharepoint_error"] = str(e)
        except Exception as e:
            logger.exception(f"Unexpected SharePoint error for project {db_project.project_code}")
            data["sharepoint_status"] = "error"
            data["sharepoint_site_url"] = None
            data["sharepoint_error"] = f"Unexpected error: {str(e)}"
    else:
        data["sharepoint_status"] = "not_requested"
        data["sharepoint_site_url"] = None

    return data


@app.get("/api/projects", response_model=List[schemas.ProjectOut])
def list_projects(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Project)
    # NOTE: Engineers see the full project list (all BU Head-created projects).
    # Task/record access remains scoped per-engineer inside each endpoint.
    return query.order_by(models.Project.created_at.desc()).all()


@app.get("/api/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # The dev database has no foreign-key cascade, so remove the project and
    # every child row explicitly (children are only ever owned by this project).
    db.query(models.WbsNode).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.WbsNodeHistory).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.GanttTask).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.ResourceBooking).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.TimeLogEntry).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.GovernanceAction).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.ExtensionRequest).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.query(models.Notification).filter_by(project_id=project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return {"ok": True, "deleted_project_id": project_id}


@app.get("/api/projects/{project_id}/sharepoint-mirror")
async def get_sharepoint_mirror(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get real SharePoint mirror data for a project.
    Accessible by BU Head, Lead, and Engineer for projects they have access to.
    """
    # Role-based access: all three roles can view
    require_role(user.role, {"bu_head", "lead", "engineer"})

    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Additional scoping: Lead and Engineer must have access to this project
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        assigned_projects = engineer_wbs_ids(db, user.employee_id, user.full_name)
        booked_projects = {
            project_id for (project_id,) in db.query(models.ResourceBooking.project_id)
            .filter_by(employee_id=user.employee_id).distinct().all()
        }
        project_ids = assigned_projects | booked_projects
        if project_id not in project_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this project.")
    elif user.role == "lead":
        if not user.full_name:
            raise HTTPException(status_code=400, detail="Lead identity is required.")
        lead_projects = db.query(models.WbsNode.project_id).filter_by(assigned_lead=user.full_name).distinct().all()
        lead_project_ids = {p[0] for p in lead_projects}
        if not lead_project_ids:
            raise HTTPException(status_code=403, detail="You are not assigned to any projects.")
        if project_id not in lead_project_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this project.")

    try:
        data = await get_sharepoint_mirror_data(project)
        return data
    except SharePointError as e:
        logger.error(f"SharePoint mirror error for project {project.project_code}: {e}")
        raise HTTPException(status_code=502, detail=f"SharePoint error: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching SharePoint mirror for project {project.project_code}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/api/engineers", response_model=List[schemas.EngineerOut])
def list_engineers(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"lead", "bu_head", "engineer"})
    return db.query(models.Employee).order_by(models.Employee.name).all()


@app.get("/api/employees", response_model=List[schemas.EngineerOut])
def list_employees(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"lead", "bu_head"})
    return db.query(models.Employee).order_by(models.Employee.name).all()


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
        "planned_hours": booking.planned_hours,
        "cost_per_hour": 0,
        "total_cost": 0,
        "utilization_rate": utilization,
        "bench_status": "Fully Booked" if utilization >= 100 else "Near Capacity" if utilization >= 80 else "Available Bench",
        "approval_status": booking.approval_status,
        "submitted_at": booking.submitted_at.isoformat() if booking.submitted_at else None,
        "approved_at": booking.approved_at.isoformat() if booking.approved_at else None,
    }


BOOKING_APPROVAL_LABELS = {
    "draft": "Draft",
    "pending_approval": "Pending Approval",
    "approved": "Approved",
}


def booking_approval_status(db: Session, project_id: int) -> str:
    """Project-level resource-booking approval state derived from its rows."""
    statuses = [
        b.approval_status
        for b in db.query(models.ResourceBooking).filter_by(project_id=project_id).all()
    ]
    if not statuses:
        return "draft"
    if set(statuses) == {"approved"}:
        return "approved"
    if "pending_approval" in statuses:
        return "pending_approval"
    return "draft"


def notification_output(notification: models.Notification) -> dict:
    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "recipient_user_id": notification.recipient_user_id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "project_id": notification.project_id,
        "actor_name": notification.actor_name,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def create_bu_head_notification(
    db: Session,
    notification_type: str,
    title: str,
    message: str,
    project_id: Optional[int] = None,
    actor_name: Optional[str] = None,
):
    """Persist a notification row for the BU Head role."""
    notification = models.Notification(
        recipient_role="bu_head",
        notification_type=notification_type,
        title=title,
        message=message,
        project_id=project_id,
        actor_name=actor_name,
    )
    db.add(notification)
    db.flush()
    return notification


@app.get("/api/projects/{project_id}/resource-bookings")
def list_resource_bookings(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"lead", "bu_head", "engineer"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    query = db.query(models.ResourceBooking).filter_by(project_id=project_id)
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter_by(employee_id=user.employee_id)
    bookings = query.all()
    return [booking_output(db, booking) for booking in bookings]


@app.get("/api/projects/{project_id}/resource-summary")
def resource_summary(project_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"lead", "bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    bookings = db.query(models.ResourceBooking).filter_by(project_id=project_id).all()
    total_hours = sum(booking.planned_hours for booking in bookings)
    return {
        "target_baseline_hours": 0,
        "total_booked_hours": total_hours,
        "allocated_pct": 0,
        "planned_labor_cost": 0,
        "contract_currency": "USD",
        "contract_value": 0,
        "available_bench_engineers": max(0, db.query(models.Employee).count() - len(bookings)),
        "project_name": project.project_name if project else "",
        "approval_status": booking_approval_status(db, project_id),
        "approval_status_label": BOOKING_APPROVAL_LABELS.get(booking_approval_status(db, project_id)),
    }


@app.post("/api/projects/{project_id}/resource-bookings")
def create_resource_booking(
    project_id: int,
    payload: dict,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    if not db.query(models.Employee).filter_by(id=payload.get("employee_id")).first():
        raise HTTPException(status_code=400, detail="Engineer not found.")
    booking = models.ResourceBooking(
        project_id=project_id,
        employee_id=int(payload["employee_id"]),
        planned_hours=int(payload.get("planned_hours", 0)),
        utilization_rate=int(payload.get("utilization_rate", 0)),
        approval_status="draft",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking_output(db, booking)


@app.post("/api/projects/{project_id}/resource-bookings/submit")
def submit_resource_bookings(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    bookings = db.query(models.ResourceBooking).filter_by(project_id=project_id).all()
    if not bookings:
        raise HTTPException(status_code=400, detail="Assign at least one engineer before submitting for approval.")
    current = booking_approval_status(db, project_id)
    if current == "pending_approval":
        raise HTTPException(status_code=409, detail="This resource booking is already pending approval.")
    if current == "approved":
        raise HTTPException(status_code=409, detail="This resource booking has already been approved.")

    now = datetime.now()
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


@app.post("/api/projects/{project_id}/resource-bookings/approve")
def approve_resource_bookings(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    bookings = db.query(models.ResourceBooking).filter_by(project_id=project_id).all()
    if not bookings:
        raise HTTPException(status_code=400, detail="No resource bookings have been assigned.")
    current = booking_approval_status(db, project_id)
    if current == "approved":
        raise HTTPException(status_code=409, detail="This resource booking has already been approved.")
    if current != "pending_approval":
        raise HTTPException(status_code=409, detail="This resource booking is not pending approval.")

    now = datetime.now()
    for booking in bookings:
        booking.approval_status = "approved"
        booking.approved_at = now
    for notification in db.query(models.Notification).filter_by(
        recipient_role="bu_head",
        notification_type="resource_booking_approval",
        project_id=project.id,
        is_read=False,
    ):
        notification.is_read = True
    db.commit()
    return {
        "status": "approved",
        "status_label": BOOKING_APPROVAL_LABELS["approved"],
    }


@app.get("/api/notifications")
def list_notifications(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user.role, {"bu_head", "lead", "engineer"})
    query = db.query(models.Notification).filter(
        (models.Notification.recipient_role == user.role)
        | (models.Notification.recipient_user_id == user.id)
    )
    notifications = query.order_by(
        models.Notification.created_at.desc(), models.Notification.id.desc()
    ).limit(50).all()
    return [notification_output(n) for n in notifications]


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(models.Notification).filter_by(id=notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if notification.recipient_role != user.role and notification.recipient_user_id != user.id:
        raise HTTPException(status_code=403, detail="This notification is not for you.")
    notification.is_read = True
    db.commit()
    return {"ok": True}


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
        if node_level(db, parent) >= 3:
            raise HTTPException(status_code=400, detail="WBS hierarchy supports three levels.")
    if payload.assigned_engineer_id is not None and not db.query(models.Employee).filter_by(id=payload.assigned_engineer_id).first():
        raise HTTPException(status_code=400, detail="Engineer not found.")


@app.get("/api/projects/{project_id}/wbs-structure", response_model=List[schemas.WbsNodeOut])
def list_wbs_structure(
    project_id: int,
    include_ancestors: bool = False,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead", "bu_head", "engineer"})
    query = db.query(models.WbsNode).filter_by(project_id=project_id)
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        assigned_nodes = query.filter(
            engineer_wbs_condition(user.employee_id, user.full_name)
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


def time_entry_total(entry) -> float:
    return sum(float(getattr(entry, field) or 0) for field in models.DAY_FIELDS)


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
):
    query = db.query(models.WbsNode).filter_by(project_id=project_id)
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter(
            engineer_wbs_condition(user.employee_id, user.full_name)
        )
    elif user.role == "lead":
        if not user.full_name:
            raise HTTPException(status_code=400, detail="Lead identity is required.")
        query = query.filter(models.WbsNode.assigned_lead == user.full_name)
    return query.order_by(models.WbsNode.wbs_code).all()


@app.get("/api/projects/{project_id}/timesheet")
def list_timesheet_entries(
    project_id: int,
    week_start: Optional[str] = None,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead", "engineer", "bu_head"})
    query = db.query(models.TimeLogEntry).filter_by(project_id=project_id)
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter_by(employee_id=user.employee_id)
    elif user.role == "lead":
        if not user.full_name:
            raise HTTPException(status_code=400, detail="Lead identity is required.")
        lead_tasks = scoped_wbs_tasks(db, project_id, user)
        task_ids = [task.id for task in lead_tasks]
        query = query.filter(models.TimeLogEntry.task_id.in_(task_ids)) if task_ids else query.filter(models.TimeLogEntry.id < 0)
    if week_start:
        query = query.filter_by(week_start_date=date.fromisoformat(week_start))
    return [time_entry_output(db, entry) for entry in query.order_by(models.TimeLogEntry.week_start_date).all()]


@app.get("/api/projects/{project_id}/timeline-logs")
def project_timeline_logs(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead", "engineer", "bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    tasks = scoped_wbs_tasks(db, project_id, user)
    task_ids = [task.id for task in tasks]

    entries_query = db.query(models.TimeLogEntry).filter_by(project_id=project_id)
    if user.role == "engineer":
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
        if task.deliverable_status == "Completed":
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
            "assigned_lead": task.assigned_lead,
            "assigned_engineer_id": task.assigned_engineer_id,
            "assigned_engineer_name": engineer.name if engineer else None,
            "estimated_hours": task.estimated_hours,
            "deliverable_status": task.deliverable_status,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "target_due_date": task.target_due_date.isoformat() if task.target_due_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "actual_hours": round(actual, 2),
            "percent_complete": percent,
        })

    total_logged = round(sum(time_entry_total(entry) for entry in entries), 2)
    entries_out = [time_entry_output(db, entry) for entry in entries]
    engineer = db.query(models.Employee).filter_by(id=user.employee_id).first() if user.role == "engineer" and user.employee_id else None

    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "scope": {
            "role": user.role,
            "engineer_id": user.employee_id if user.role == "engineer" else None,
            "engineer_name": engineer.name if engineer else None,
            "lead_name": user.full_name if user.role == "lead" else None,
        },
        "tasks": tasks_out,
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
            "completed_tasks": sum(1 for task in tasks if task.deliverable_status == "Completed"),
            "engineer_count": len(engineers),
        },
    }


@app.get("/api/engineer-performance", response_model=schemas.EngineerPerformanceOut)
def engineer_performance(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"engineer"})
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    employee = db.query(models.Employee).filter_by(id=user.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found for this account.")

    nodes = db.query(models.WbsNode).filter(
        engineer_wbs_condition(user.employee_id, user.full_name)
    ).order_by(models.WbsNode.wbs_code).all()
    entries = (
        db.query(models.TimeLogEntry)
        .filter_by(employee_id=user.employee_id)
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
        if node.deliverable_status == "Completed":
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
            "completed_tasks": sum(1 for node in nodes if node.deliverable_status == "Completed"),
            "scheduled_hours": scheduled_hours,
            "logged_hours": total_logged,
            "approved_hours": approved_hours,
            "pending_hours": pending_hours,
            "completion_pct": round((sum(1 for node in nodes if node.deliverable_status == "Completed") / len(nodes)) * 100) if nodes else 0,
            "allocation_pct": round((total_logged / scheduled_hours) * 100) if scheduled_hours else 0,
        },
        "projects": [row for row in per_project.values()],
        "recent_entries": recent_entries,
    }


def engineer_dashboard_data(db: Session, employee_id: int, full_name: str | None = None):
    """Compute engineer-scoped dashboard metrics from approved time entries."""
    from datetime import datetime, date
    from collections import defaultdict
    import calendar

    # Get all WBS nodes assigned to this engineer (by employee id OR by name)
    nodes = db.query(models.WbsNode).filter(
        engineer_wbs_condition(employee_id, full_name)
    ).all()
    if not nodes:
        return {
            "summary": {
                "total_hours_consumption": 0.0,
                "total_hours_scheduled": 0,
                "total_hours_approved": 0.0,
                "total_hours_pending": 0.0,
                "consumption_pct": 0.0,
                "governance_status": "normal",
                "governance_threshold_pct": None,
                "governance_exceeded": False,
                "spi_value": None,
                "spi_note": "No assigned tasks.",
            },
            "projects": [],
            "monthly_breakdown": [],
        }

    project_ids = {node.project_id for node in nodes}
    projects = db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()
    project_by_id = {project.id: project for project in projects}

    # Get all approved/pending time entries for this engineer across their projects
    entries = db.query(models.TimeLogEntry).filter_by(employee_id=employee_id).all()

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
            "completed_tasks": 0,
        }

    for node in nodes:
        row = per_project.get(node.project_id)
        if row:
            row["scheduled_hours"] += node.estimated_hours or 0
            row["total_tasks"] += 1
            if node.deliverable_status == "Completed":
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

    # Compute per-project governance threshold status for the engineer
    for project_id in project_ids:
        row = per_project[project_id]
        threshold = row["governance_threshold_pct"]
        scheduled = row["scheduled_hours"]
        logged = row["logged_hours"]
        pct = round((logged / scheduled) * 100, 1) if scheduled else 0.0
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

    # Aggregate consumed hours by month, splitting normal vs exceeded per project
    for entry in entries:
        total = time_entry_total(entry)
        if total <= 0:
            continue
        month_key = _get_month_key(entry.week_start_date)
        project_row = per_project.get(entry.project_id)
        if project_row and project_row.get("exceeded"):
            monthly_consumed_exceeded[month_key] += total
        else:
            monthly_consumed_normal[month_key] += total

    # Collect all months that have data and sort them
    all_months = sorted(set(monthly_planned.keys()) | set(monthly_consumed_normal.keys()) | set(monthly_consumed_exceeded.keys()))

    monthly_breakdown = []
    for month_key in all_months:
        planned = round(monthly_planned.get(month_key, 0.0), 1)
        normal = round(monthly_consumed_normal.get(month_key, 0.0), 1)
        exceeded = round(monthly_consumed_exceeded.get(month_key, 0.0), 1)
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

    # Compute totals across all projects
    total_scheduled = sum(p["scheduled_hours"] for p in per_project.values())
    total_approved = sum(p["approved_hours"] for p in per_project.values())
    total_logged = sum(p["logged_hours"] for p in per_project.values())
    total_pending = sum(p["pending_hours"] for p in per_project.values())

    consumption_pct = round((total_logged / total_scheduled) * 100, 1) if total_scheduled else 0.0

    # Governance threshold status (use max threshold across projects, or first project's threshold)
    thresholds = [p["governance_threshold_pct"] for p in per_project.values() if p["governance_threshold_pct"] is not None]
    governance_threshold = max(thresholds) if thresholds else None
    governance_exceeded = governance_threshold is not None and consumption_pct > governance_threshold
    governance_status = "exceeded" if governance_exceeded else "normal"

    # SPI = approved_hours / scheduled_hours
    spi_value = round(total_approved / total_scheduled, 2) if total_scheduled else None
    if not total_scheduled:
        spi_note = "No baseline planned hours for assigned tasks yet."
    elif spi_value >= 1.0:
        spi_note = f"Earned hours ({total_approved:g}) match or exceed the planned baseline ({total_scheduled:g})."
    else:
        spi_note = f"Behind plan — {total_approved:g} earned of {total_scheduled:g} planned baseline hours."

    # Convert projects to list
    projects_list = list(per_project.values())

    return {
        "summary": {
            "total_hours_consumption": round(total_logged, 2),
            "total_hours_scheduled": total_scheduled,
            "total_hours_approved": round(total_approved, 2),
            "total_hours_pending": round(total_pending, 2),
            "consumption_pct": consumption_pct,
            "governance_status": governance_status,
            "governance_threshold_pct": governance_threshold,
            "governance_exceeded": governance_exceeded,
            "spi_value": spi_value,
            "spi_note": spi_note,
        },
        "projects": projects_list,
        "monthly_breakdown": monthly_breakdown,
    }


@app.get("/api/engineer-performance-dashboard", response_model=schemas.EngineerDashboardOut)
def engineer_performance_dashboard(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"engineer"})
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    employee = db.query(models.Employee).filter_by(id=user.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee record not found for this account.")

    return engineer_dashboard_data(db, user.employee_id, user.full_name)


@app.get("/api/projects/{project_id}/work-summary")
def project_work_summary(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    nodes = db.query(models.WbsNode).filter_by(project_id=project_id).order_by(models.WbsNode.wbs_code).all()
    entries = db.query(models.TimeLogEntry).filter_by(project_id=project_id).all()
    node_by_id = {node.id: node for node in nodes}

    phase_stats = defaultdict(lambda: {"total": 0, "completed": 0})
    lead_phases = defaultdict(set)
    lead_phase_stats = defaultdict(lambda: defaultdict(lambda: {"total": 0, "completed": 0}))
    lead_nodes = defaultdict(int)
    eng_tasks = defaultdict(list)
    eng_logged = defaultdict(float)
    eng_approved = defaultdict(float)
    eng_pending = defaultdict(float)
    lead_logged = defaultdict(float)
    lead_approved = defaultdict(float)
    lead_pending_entries = defaultdict(int)
    task_eng_approved = defaultdict(float)

    for node in nodes:
        if node.phase:
            phase_stats[node.phase]["total"] += 1
            if node.deliverable_status == "Completed":
                phase_stats[node.phase]["completed"] += 1
        if node.assigned_lead:
            lead_phases[node.assigned_lead].add(node.phase or "")
            lead_nodes[node.assigned_lead] += 1
            if node.phase:
                lead_phase_stats[node.assigned_lead][node.phase]["total"] += 1
                if node.deliverable_status == "Completed":
                    lead_phase_stats[node.assigned_lead][node.phase]["completed"] += 1
        if node.assigned_engineer_id:
            eng_tasks[node.assigned_engineer_id].append(node)

    for entry in entries:
        total = time_entry_total(entry)
        task = node_by_id.get(entry.task_id)
        lead = task.assigned_lead if task else None
        eng_logged[entry.employee_id] += total
        if lead:
            lead_logged[lead] += total
        if entry.approval_status == "approved":
            eng_approved[entry.employee_id] += total
            task_eng_approved[(entry.task_id, entry.employee_id)] += total
            if lead:
                lead_approved[lead] += total
        elif entry.approval_status == "pending_review":
            eng_pending[entry.employee_id] += total
            if lead:
                lead_pending_entries[lead] += 1

    engineer_ids = sorted({node.assigned_engineer_id for node in nodes if node.assigned_engineer_id})
    employees = (
        {employee.id: employee
         for employee in db.query(models.Employee).filter(models.Employee.id.in_(engineer_ids)).all()}
        if engineer_ids else {}
    )

    leads_out = []
    for lead_name in sorted(lead_nodes):
        phases = sorted(phase for phase in lead_phases[lead_name] if phase)
        leads_out.append({
            "name": lead_name,
            "phases": phases,
            "nodes_managed": lead_nodes[lead_name],
            "phase_completion": {
                phase: dict(lead_phase_stats[lead_name][phase]) for phase in phases
            },
            "approved_hours": round(lead_approved[lead_name], 2),
            "logged_hours": round(lead_logged[lead_name], 2),
            "pending_approvals": lead_pending_entries[lead_name],
        })

    engineers_out = []
    for engineer_id in engineer_ids:
        employee = employees.get(engineer_id)
        if employee is None:
            continue
        tasks = sorted(eng_tasks.get(engineer_id, []), key=lambda task: str(task.wbs_code or ""))
        statuses = {task.deliverable_status for task in tasks}
        if "In Progress" in statuses:
            progress_status = "In Progress"
        elif "Not Started" in statuses:
            progress_status = "Not Started"
        elif statuses and "Completed" == list(statuses)[0]:
            progress_status = "Completed"
        else:
            progress_status = "—"
        engineers_out.append({
            "employee_id": employee.id,
            "name": employee.name,
            "role_title": employee.role_title,
            "discipline": employee.discipline,
            "phases": sorted({task.phase for task in tasks if task.phase}),
            "assigned_nodes": len(tasks),
            "baseline_hours": sum(task.estimated_hours or 0 for task in tasks),
            "approved_hours": round(eng_approved[engineer_id], 2),
            "logged_hours": round(eng_logged[engineer_id], 2),
            "pending_hours": round(eng_pending[engineer_id], 2),
            "progress_status": progress_status,
            "tasks": [
                {
                    "task_id": task.id,
                    "wbs_code": task.wbs_code,
                    "task_name": task.task_name,
                    "phase": task.phase,
                    "status": task.deliverable_status,
                    "estimated_hours": task.estimated_hours,
                    "approved_hours": round(task_eng_approved.get((task.id, engineer_id), 0.0), 2),
                }
                for task in tasks
            ],
        })

    return {
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "project_code": project.project_code,
            "client_organization": project.client_organization,
            "project_lead": project.project_lead,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "target_end_date": project.target_end_date.isoformat() if project.target_end_date else None,
        },
        "leads": leads_out,
        "engineers": engineers_out,
        "phase_completion": {phase: stats for phase, stats in phase_stats.items()},
        "summary": {
            "total_nodes": len(nodes),
            "completed_nodes": sum(1 for node in nodes if node.deliverable_status == "Completed"),
            "scheduled_hours": sum(node.estimated_hours or 0 for node in nodes),
            "approved_hours": round(sum(eng_approved.values()), 2),
            "logged_hours": round(sum(eng_logged.values()), 2),
            "pending_hours": round(sum(eng_pending.values()), 2),
            "pending_entries": sum(lead_pending_entries.values()),
        },
    }


def _get_month_key(dt: date) -> str:
    """Convert a date to a YYYY-MM string for monthly grouping."""
    return dt.strftime("%Y-%m")


def _distribute_hours_over_months(total_hours: float, start_date: date | None, end_date: date | None) -> dict[str, float]:
    """Distribute total hours evenly across months between start_date and end_date (inclusive)."""
    if not start_date or not end_date or total_hours <= 0:
        return {}
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    from calendar import monthrange

    current = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    months = []
    while current <= end_month:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if not months:
        return {}

    hours_per_month = total_hours / len(months)
    result = {}
    for month_start in months:
        key = _get_month_key(month_start)
        result[key] = round(hours_per_month, 2)
    return result


def executive_dashboard_data(db: Session, project: models.Project) -> dict:
    """Roll up the real project data every governance view consumes.

    Budget burn, hours consumption, threshold status and SPI are all
    derived from stored rows (wbs_nodes, time_log_entries, employees,
    projects) — no mock values.
    """
    nodes = db.query(models.WbsNode).filter_by(project_id=project.id).all()
    entries = db.query(models.TimeLogEntry).filter_by(project_id=project.id).all()

    scheduled_hours = sum(node.estimated_hours or 0 for node in nodes)
    logged_hours = 0.0
    approved_hours = 0.0
    pending_hours = 0.0
    pending_entries = 0
    for entry in entries:
        total = time_entry_total(entry)
        logged_hours += total
        if entry.approval_status == "approved":
            approved_hours += total
        elif entry.approval_status == "pending_review":
            pending_hours += total
            pending_entries += 1

    consumption_pct = round(logged_hours / scheduled_hours * 100, 1) if scheduled_hours else 0.0

    engineer_ids = sorted({node.assigned_engineer_id for node in nodes if node.assigned_engineer_id})
    employees = (
        {employee.id: employee
         for employee in db.query(models.Employee).filter(models.Employee.id.in_(engineer_ids)).all()}
        if engineer_ids else {}
    )

    eng_baseline = defaultdict(float)
    eng_consumed = defaultdict(float)
    eng_approved = defaultdict(float)
    eng_pending = defaultdict(float)
    eng_pending_entries = defaultdict(int)
    for node in nodes:
        if node.assigned_engineer_id:
            eng_baseline[node.assigned_engineer_id] += node.estimated_hours or 0
    for entry in entries:
        eng_consumed[entry.employee_id] += time_entry_total(entry)
        if entry.approval_status == "approved":
            eng_approved[entry.employee_id] += time_entry_total(entry)
        elif entry.approval_status == "pending_review":
            eng_pending[entry.employee_id] += time_entry_total(entry)
            eng_pending_entries[entry.employee_id] += 1

    disciplines = defaultdict(lambda: {
        "baseline_hours": 0.0,
        "consumed_hours": 0.0,
        "approved_hours": 0.0,
        "pending_hours": 0.0,
        "pending_entries": 0,
        "engineer_count": 0,
    })
    for engineer_id in engineer_ids:
        employee = employees.get(engineer_id)
        if employee is None:
            continue
        discipline = employee.discipline or "Unassigned"
        disc = disciplines[discipline]
        disc["baseline_hours"] += eng_baseline.get(engineer_id, 0.0)
        disc["consumed_hours"] += eng_consumed.get(engineer_id, 0.0)
        disc["approved_hours"] += eng_approved.get(engineer_id, 0.0)
        disc["pending_hours"] += eng_pending.get(engineer_id, 0.0)
        disc["pending_entries"] += eng_pending_entries.get(engineer_id, 0)
        disc["engineer_count"] += 1

    threshold = project.governance_threshold_pct
    threshold_active = threshold is not None
    disciplines_out = []
    exceptions = []
    for name in sorted(disciplines):
        disc = disciplines[name]
        pct = round(disc["consumed_hours"] / disc["baseline_hours"] * 100, 1) if disc["baseline_hours"] else 0.0
        exceeded = threshold_active and disc["baseline_hours"] > 0 and pct > threshold
        disciplines_out.append({
            "name": name,
            "baseline_hours": round(disc["baseline_hours"], 1),
            "consumed_hours": round(disc["consumed_hours"], 1),
            "approved_hours": round(disc["approved_hours"], 1),
            "pending_hours": round(disc["pending_hours"], 1),
            "pending_entries": disc["pending_entries"],
            "consumption_pct": pct,
            "exceeded": exceeded,
            "engineer_count": disc["engineer_count"],
        })
        if exceeded:
            exceptions.append({
                "discipline": name,
                "consumption_pct": pct,
                "threshold_pct": threshold,
                "consumed_hours": round(disc["consumed_hours"], 1),
                "baseline_hours": round(disc["baseline_hours"], 1),
                "pending_hours": round(disc["pending_hours"], 1),
                "pending_entries": disc["pending_entries"],
            })

    max_discipline = max(disciplines_out, key=lambda d: d["consumption_pct"], default=None)
    max_pct = max_discipline["consumption_pct"] if max_discipline else consumption_pct
    over_threshold = threshold_active and (bool(exceptions) or (max_discipline is not None and max_pct > threshold))
    status = "exceeded" if over_threshold else "normal"

    spi_value = round(approved_hours / scheduled_hours, 2) if scheduled_hours else None
    if not scheduled_hours:
        spi_note = "No baseline planned hours for this project yet."
    elif spi_value >= 1.0:
        spi_note = f"Earned hours ({approved_hours:g}) match or exceed the planned baseline ({scheduled_hours:g})."
    else:
        spi_note = f"Behind plan — {approved_hours:g} earned of {scheduled_hours:g} planned baseline hours."

    currency = project.contract_currency or "USD"
    contract_value = float(project.contract_value or 0)
    budget_consumed = round(contract_value * (logged_hours / scheduled_hours), 2) if scheduled_hours and contract_value else 0.0
    budget_pct = round(budget_consumed / contract_value * 100, 1) if contract_value else 0.0

    # Monthly data aggregation for the vertical grouped bar chart
    monthly_planned = defaultdict(float)
    monthly_consumed_normal = defaultdict(float)
    monthly_consumed_exceeded = defaultdict(float)

    # Distribute planned hours (baseline) across months based on WBS node dates
    for node in nodes:
        if node.estimated_hours and node.estimated_hours > 0:
            start = node.start_date
            end = node.target_due_date or node.end_date
            distributed = _distribute_hours_over_months(float(node.estimated_hours), start, end)
            for month_key, hours in distributed.items():
                monthly_planned[month_key] += hours

    # Aggregate actual consumed hours by month from time log entries
    for entry in entries:
        total = time_entry_total(entry)
        if total <= 0:
            continue
        month_key = _get_month_key(entry.week_start_date)
        # Check if this entry's discipline exceeded threshold
        employee = None
        for emp in employees.values():
            if emp.id == entry.employee_id:
                employee = emp
                break
        discipline = employee.discipline if employee else "Unassigned"
        disc_exceeded = any(d["name"] == discipline and d["exceeded"] for d in disciplines_out)
        if disc_exceeded:
            monthly_consumed_exceeded[month_key] += total
        else:
            monthly_consumed_normal[month_key] += total

    # Collect all months that have data and sort them
    all_months = sorted(set(monthly_planned.keys()) | set(monthly_consumed_normal.keys()) | set(monthly_consumed_exceeded.keys()))

    monthly_data = []
    for month_key in all_months:
        planned = round(monthly_planned.get(month_key, 0.0), 1)
        normal = round(monthly_consumed_normal.get(month_key, 0.0), 1)
        exceeded = round(monthly_consumed_exceeded.get(month_key, 0.0), 1)
        # Format month label as "MMM YYYY" (e.g., "Jun 2025")
        try:
            year, month = map(int, month_key.split("-"))
            month_label = date(year, month, 1).strftime("%b %Y")
        except Exception:
            month_label = month_key
        monthly_data.append({
            "month": month_key,
            "month_label": month_label,
            "planned_baseline": planned,
            "normal_consumption": normal,
            "exceeded_threshold": exceeded,
        })

    return {
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "project_code": project.project_code,
            "client_organization": project.client_organization,
            "project_lead": project.project_lead,
            "contract_value": round(contract_value, 2),
            "contract_currency": currency,
            "governance_threshold_pct": threshold,
            "timesheets_soft_locked": bool(project.timesheets_soft_locked),
            "extension_status": project.extension_status,
            "extension_approved_hours": project.extension_approved_hours,
        },
        "summary": {
            "scheduled_hours": scheduled_hours,
            "approved_hours": round(approved_hours, 2),
            "logged_hours": round(logged_hours, 2),
            "pending_hours": round(pending_hours, 2),
            "pending_entries": pending_entries,
            "consumption_pct": consumption_pct,
        },
        "commercial_budget_burn": {
            "currency": currency,
            "total": round(contract_value, 2),
            "consumed": budget_consumed,
            "remaining": round(contract_value - budget_consumed, 2),
            "percent": budget_pct,
        },
        "hours_consumption": {
            "hours": round(logged_hours, 2),
            "scheduled": scheduled_hours,
            "approved": round(approved_hours, 2),
            "pending": round(pending_hours, 2),
            "percent": consumption_pct,
        },
        "governance_status": {
            "status": status,
            "threshold_pct": threshold,
            "consumption_pct": consumption_pct,
            "max_discipline_pct": max_pct,
            "max_discipline": max_discipline["name"] if max_discipline else None,
            "soft_locked": bool(project.timesheets_soft_locked),
        },
        "spi": {"value": spi_value, "note": spi_note},
        "disciplines": disciplines_out,
        "exceptions": exceptions,
        "monthly_data": monthly_data,
    }


@app.get("/api/projects/{project_id}/executive-dashboard")
def executive_dashboard(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead", "bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    data = executive_dashboard_data(db, project)
    actions = (
        db.query(models.GovernanceAction)
        .filter_by(project_id=project_id)
        .order_by(models.GovernanceAction.created_at.desc(), models.GovernanceAction.id.desc())
        .all()
    )
    requests = (
        db.query(models.ExtensionRequest)
        .filter_by(project_id=project_id)
        .order_by(models.ExtensionRequest.requested_at.desc(), models.ExtensionRequest.id.desc())
        .all()
    )
    if user.role == "lead":
        requests = [request for request in requests if request.requested_by_user_id == user.id]
    data["extension_requests"] = [extension_request_output(db, request) for request in requests]
    data["current_extension_request"] = next(
        (request for request in data["extension_requests"] if request["status"] == "pending"),
        None,
    )
    data["governance_actions"] = [
        {
            "id": action.id,
            "action": action.action,
            "discipline": action.discipline,
            "consumption_pct": action.consumption_pct,
            "threshold_pct": action.threshold_pct,
            "consumption_hours": action.consumption_hours,
            "comments": action.comments,
            "created_by": action.created_by,
            "extension_request_id": action.extension_request_id,
            "requested_hours": action.requested_hours,
            "created_at": action.created_at.isoformat() if action.created_at else None,
        }
        for action in actions
    ]
    return data


@app.post("/api/projects/{project_id}/extension-requests", response_model=schemas.ExtensionRequestOut, status_code=201)
def create_extension_request_endpoint(
    project_id: int,
    payload: schemas.ExtensionRequestCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    request = create_extension_request(
        db,
        project,
        user,
        payload.requested_hours,
        payload.justification,
    )
    return extension_request_output(db, request)


@app.post("/api/projects/{project_id}/extension-requests/{request_id}/decision", response_model=schemas.ExtensionRequestOut)
def decide_extension_request_endpoint(
    project_id: int,
    request_id: int,
    payload: schemas.ExtensionRequestDecision,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    request = db.query(models.ExtensionRequest).filter_by(id=request_id, project_id=project_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Extension request not found.")
    request = decide_extension_request(
        db,
        project,
        request,
        payload.decision,
        payload.comments,
        user,
    )
    return extension_request_output(db, request)


def record_governance_action(
    db: Session,
    project: models.Project,
    action: str,
    payload: schemas.GovernanceActionBase,
    created_by_name: str,
) -> models.GovernanceAction:
    data = executive_dashboard_data(db, project)
    return models.GovernanceAction(
        project_id=project.id,
        action=action,
        discipline=payload.discipline or data["governance_status"]["max_discipline"],
        consumption_pct=data["governance_status"]["max_discipline_pct"],
        threshold_pct=project.governance_threshold_pct,
        consumption_hours=data["summary"]["logged_hours"],
        comments=payload.comments,
        created_by=created_by_name,
    )


@app.post("/api/projects/{project_id}/governance/stop-execution", response_model=schemas.GovernanceActionOut)
def stop_execution(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    action = record_governance_action(db, project, "stop_execution", payload, user.full_name)
    db.add(action)
    project.timesheets_soft_locked = True
    db.commit()
    db.refresh(action)
    return action


@app.post("/api/projects/{project_id}/governance/reject-extension", response_model=schemas.GovernanceActionOut)
def reject_extension(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    request = find_pending_extension_request(db, project_id)
    if not request:
        raise HTTPException(status_code=409, detail="No pending extension request is available to reject.")
    request = decide_extension_request(db, project, request, "reject", payload.comments, user)
    action = (
        db.query(models.GovernanceAction)
        .filter_by(extension_request_id=request.id, action="reject_extension")
        .order_by(models.GovernanceAction.id.desc())
        .first()
    )
    return action


@app.post("/api/projects/{project_id}/governance/request-extension", response_model=schemas.GovernanceActionOut)
def request_extension(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    requested_hours = parse_legacy_requested_hours(payload.comments)
    request = create_extension_request(db, project, user, requested_hours, payload.comments)
    action = (
        db.query(models.GovernanceAction)
        .filter_by(extension_request_id=request.id, action="extension_request")
        .order_by(models.GovernanceAction.id.desc())
        .first()
    )
    return action


@app.post("/api/projects/{project_id}/governance/approve-extension", response_model=schemas.GovernanceActionOut)
def approve_extension(
    project_id: int,
    payload: schemas.GovernanceActionBase,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"bu_head"})
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    request = find_pending_extension_request(db, project_id)
    if not request:
        raise HTTPException(status_code=409, detail="No pending extension request is available to approve.")
    request = decide_extension_request(db, project, request, "approve", payload.comments, user)
    action = (
        db.query(models.GovernanceAction)
        .filter_by(extension_request_id=request.id, action="approve_extension")
        .order_by(models.GovernanceAction.id.desc())
        .first()
    )
    return action


@app.post("/api/projects/{project_id}/timesheet-entries")
def submit_time_log(
    project_id: int,
    payload: schemas.TimeLogEntryCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"engineer"})
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
    project = db.query(models.Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.timesheets_soft_locked:
        raise HTTPException(
            status_code=409,
            detail="Timesheets are soft-locked by the BU Head — no new entries can be logged.",
        )
    task = db.query(models.WbsNode).filter_by(id=payload.task_id, project_id=project_id).first()
    if not task:
        raise HTTPException(status_code=400, detail="Task not found in this project.")
    if not node_assigned_to_engineer(task, user):
        raise HTTPException(
            status_code=403,
            detail="You may only log hours against tasks assigned to you.",
        )
    entry = (
        db.query(models.TimeLogEntry)
        .filter_by(
            project_id=project_id,
            task_id=task.id,
            employee_id=user.employee_id,
            week_start_date=payload.week_start_date,
        )
        .first()
    )
    if entry:
        for field in models.DAY_FIELDS:
            setattr(entry, field, getattr(payload, field))
        entry.approval_status = "pending_review"
    else:
        entry = models.TimeLogEntry(
            project_id=project_id,
            task_id=task.id,
            employee_id=user.employee_id,
            week_start_date=payload.week_start_date,
            **{field: getattr(payload, field) for field in models.DAY_FIELDS},
        )
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return time_entry_output(db, entry)


def lead_review_time_log(db: Session, entry_id: int, user: models.User, status: str):
    require_role(user.role, {"lead"})
    if not user.full_name:
        raise HTTPException(status_code=400, detail="Lead identity is required.")
    entry = db.query(models.TimeLogEntry).filter_by(id=entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Time log entry not found.")
    task = db.query(models.WbsNode).filter_by(id=entry.task_id).first()
    if not task or task.assigned_lead != user.full_name:
        raise HTTPException(status_code=403, detail="This time log is outside your lead scope.")
    project = db.query(models.Project).filter_by(id=entry.project_id).first()
    if project and project.timesheets_soft_locked:
        raise HTTPException(
            status_code=409,
            detail="Timesheets are soft-locked by the BU Head — approvals are on hold.",
        )
    entry.approval_status = status
    entry.reviewed_by = user.full_name
    entry.reviewed_at = datetime.now()
    db.commit()
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


def cascade_phase(db: Session, parent_id: int, phase: str):
    for child in db.query(models.WbsNode).filter_by(parent_id=parent_id).all():
        if child.phase != phase:
            child.phase = phase
        cascade_phase(db, child.id, phase)


@app.post("/api/projects/{project_id}/wbs-nodes", response_model=schemas.WbsNodeOut, status_code=201)
def create_wbs_node(
    project_id: int,
    payload: schemas.WbsNodeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    if not db.query(models.Project).filter_by(id=project_id).first():
        raise HTTPException(status_code=404, detail="Project not found.")
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
    node_data["phase"] = phase
    node = models.WbsNode(project_id=project_id, **node_data)
    db.add(node)
    db.commit()
    db.refresh(node)
    if payload.subtask and payload.subtask.strip() and node_level(db, node) < 3:
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
            estimated_hours=None,
            deliverable_status="Not Started",
            start_date=node.start_date,
            target_due_date=node.target_due_date,
            end_date=node.end_date,
            phase=node.phase,
        )
        db.add(child)
        db.commit()
    return node_output(db, node)


@app.put("/api/wbs-nodes/{node_id}", response_model=schemas.WbsNodeOut)
def update_wbs_node(
    node_id: int,
    payload: schemas.WbsNodeUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    validate_node_payload(db, node.project_id, payload)
    duplicate = None
    if payload.wbs_code:
        duplicate = db.query(models.WbsNode).filter(models.WbsNode.project_id == node.project_id, models.WbsNode.wbs_code == payload.wbs_code, models.WbsNode.id != node_id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="WBS code already exists in this project.")
    for field, value in payload.model_dump(exclude={"subtask", "phase"}).items():
        setattr(node, field, value)
    phase_changed = payload.phase is not None and payload.phase != node.phase
    if payload.phase is not None:
        node.phase = payload.phase
    db.commit()
    if phase_changed:
        cascade_phase(db, node.id, node.phase)
        db.commit()
    db.refresh(node)
    return node_output(db, node)


def parse_wbs_upload(upload: UploadFile, content: bytes):
    filename = (upload.filename or "").lower()
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        if filename.endswith(".xls"):
            raise HTTPException(status_code=415, detail="Use .xlsx or .csv format for WBS upload.")
        namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            shared = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in shared_root.findall("main:si", namespace)]
            sheet_name = "xl/worksheets/sheet1.xml"
            sheet_root = ElementTree.fromstring(workbook.read(sheet_name))
            rows = []
            for row in sheet_root.findall(".//main:row", namespace):
                values = []
                for cell in row.findall("main:c", namespace):
                    value = cell.find("main:v", namespace)
                    text = value.text if value is not None else ""
                    if cell.get("t") == "s" and text:
                        text = shared[int(text)]
                    values.append(text)
                rows.append(values)
        if not rows:
            return []
        headers = [str(value or "").strip() for value in rows[0]]
        return [dict(zip(headers, row)) for row in rows[1:]]
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


@app.post("/api/projects/{project_id}/wbs-upload")
async def upload_wbs(
    project_id: int,
    file: UploadFile = File(...),
    phase: Optional[str] = Form(None),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    requested_phase = phase.strip() if phase and phase.strip() else None
    if requested_phase and requested_phase not in schemas.WBS_PHASES:
        raise HTTPException(status_code=422, detail=f"Phase '{requested_phase}' is not one of the five fixed phases.")
    rows = parse_wbs_upload(file, await file.read())
    if not rows:
        raise HTTPException(status_code=400, detail="The WBS file contains no rows.")
    created = updated = 0
    code_to_id = {node.wbs_code: node.id for node in db.query(models.WbsNode).filter_by(project_id=project_id).all()}
    for row in rows:
        normalized = {str(key).strip().lower().replace(" ", "_"): value for key, value in row.items()}
        code = str(normalized.get("wbs_code") or normalized.get("code") or "").strip()
        task_name = str(normalized.get("task_name") or normalized.get("task") or normalized.get("name") or "").strip()
        if not code or not task_name:
            raise HTTPException(status_code=422, detail="Each WBS row needs WBS Code and Task Name.")
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
        payload = schemas.WbsNodeUpdate(
            wbs_code=code,
            task_name=task_name,
            parent_id=parent_id,
            assigned_lead=normalized.get("assigned_lead") or None,
            assigned_engineer_id=int(normalized["assigned_engineer_id"]) if normalized.get("assigned_engineer_id") else None,
            estimated_hours=int(float(normalized.get("estimated_hours") or normalized.get("planned_hours") or 0)),
            deliverable_status=normalized.get("deliverable_status") or normalized.get("status") or "Not Started",
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
    return {"created": created, "updated": updated, "phase": requested_phase or None}


@app.get("/api/projects/{project_id}/wbs-tasks", response_model=List[schemas.WbsTaskOut])
def list_wbs_tasks(
    project_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead", "engineer", "bu_head"})
    query = db.query(models.GanttTask).filter_by(project_id=project_id)
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        query = query.filter_by(assigned_engineer_id=user.employee_id)
    return [task_output(db, task) for task in query.order_by(models.GanttTask.wbs_code).all()]


@app.put("/api/wbs-tasks/{task_id}", response_model=schemas.WbsTaskOut)
def update_wbs_task(
    task_id: int,
    payload: schemas.WbsTaskUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user.role, {"lead"})
    task = db.query(models.GanttTask).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="WBS task not found.")
    if payload.assigned_engineer_id is not None and not db.query(models.Employee).filter_by(id=payload.assigned_engineer_id).first():
        raise HTTPException(status_code=400, detail="Engineer not found.")
    task.task_name = payload.task_name.strip()
    task.wbs_code = payload.wbs_code.strip()
    task.status = payload.status
    task.planned_hours = payload.planned_hours
    task.assigned_engineer_id = payload.assigned_engineer_id
    db.commit()
    db.refresh(task)
    return task_output(db, task)


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
    if user.role == "engineer":
        if not user.employee_id:
            raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")
        if not node_assigned_to_engineer(node, user):
            raise HTTPException(status_code=403, detail="You can only view tasks assigned to you.")
    elif user.role == "lead":
        if node.assigned_lead and node.assigned_lead != user.full_name:
            has_scope = False
            if node.assigned_engineer_id:
                eng = db.query(models.Employee).filter_by(id=node.assigned_engineer_id).first()
                if eng and eng.name == user.full_name:
                    has_scope = True
            if not has_scope:
                raise HTTPException(status_code=403, detail="You can only view tasks assigned under your scope.")
    elif user.role == "bu_head":
        pass
    else:
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
    ntype = "subtask" if node.parent_id else "task"
    display_status = map_status_for_display(node.deliverable_status)

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
        history=[schemas.WbsNodeHistoryOut.model_validate(h) for h in history],
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
    if user.role != "engineer":
        raise HTTPException(status_code=403, detail="Only engineers can advance task status.")
    if not user.employee_id:
        raise HTTPException(status_code=403, detail="Engineer account is not linked to an employee.")

    node = db.query(models.WbsNode).filter_by(id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="WBS node not found.")
    if not node_assigned_to_engineer(node, user):
        raise HTTPException(status_code=403, detail="You can only update tasks assigned to you.")

    validation_error = validate_status_transition(node.deliverable_status, payload.new_status, node)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    old_status = map_status_for_display(node.deliverable_status)
    node.deliverable_status = payload.new_status

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


@app.post("/api/wbs-nodes/{node_id}/comments")
def add_wbs_node_comment(
    node_id: int,
    payload: schemas.WbsNodeCommentInput,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "engineer":
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
    now = datetime.now()
    return {
        "date": now.date().isoformat(),
        "datetime": now.isoformat(),
        "timezone": "UTC"
    }


@app.get("/health")
def health():
    return {"status": "ok"}
