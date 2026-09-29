"""Project lifecycle owned by the BU Head: lead lookup, create (with SharePoint
provisioning), list, read, archive/unarchive and delete."""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from app.core.errors import NO_PROJECT_ACCESS, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.domain.allocation import planned_hours
from app.integrations.sharepoint import DocumentStorage, SharePointError
from app.repositories.bookings import ENGINEER, LEAD, BookingRepository
from app.repositories.projects import ProjectRepository
from app.repositories.users import UserRepository
from app.services import notifications as notify
from app.services.access import project_roles, user_can_access_project, visible_project_ids
from app.services.allocation import over_capacity_message
from app.services.archive_guard import ARCHIVED_READ_ONLY, lifecycle_writes
from app.services.governance_monitor import GovernanceMonitor
from app.services.tracking import PROJECT_ARCHIVED, end_session

logger = logging.getLogger(__name__)

DUPLICATE_CODE = "Project Code already exists"
PROJECT_NOT_FOUND = "Project not found"
HAS_HISTORY = "This project has recorded work or history. Archive it instead of deleting it."
CURRENCY_CHANGE = (
    "Changing the currency relabels the contract value and budget burn; amounts are not converted. "
    "Confirm the change to proceed."
)

# The three project lead slots: (name column, user id column).
_LEAD_SLOTS = (
    ("project_lead_electrical", "project_lead_electrical_user_id"),
    ("project_lead_mechanical", "project_lead_mechanical_user_id"),
    ("project_lead_bim", "project_lead_bim_user_id"),
)
# Fields recorded (before -> after) in the audit log when a project is edited.
_AUDITED_FIELDS = {
    "project_name": "Project name",
    "project_code": "Project code",
    "client_organization": "Client",
    "start_date": "Target start date",
    "contract_value": "Contract value",
    "contract_currency": "Currency",
    "target_effort_hours": "Target effort hours",
    "governance_threshold_pct": "Alert threshold %",
    "project_lead_electrical": "Electrical lead",
    "project_lead_mechanical": "Mechanical lead",
    "project_lead_bim": "BIM lead",
}

EXTENSION_CANCELLED = "cancelled"


class ProjectService:
    def __init__(
        self,
        db: Session,
        projects: ProjectRepository,
        users: UserRepository,
        bookings: BookingRepository,
        storage: DocumentStorage,
        monitor: GovernanceMonitor,
    ):
        self.db = db
        self.projects = projects
        self.users = users
        self.bookings = bookings
        self.storage = storage
        self.monitor = monitor

    def list_leads(self) -> list[schemas.ProjectLeadOut]:
        """Everyone with an employee record, for the lead dropdowns: any of them can lead a project."""
        return [
            schemas.ProjectLeadOut(id=user.id, name=user.full_name or user.username, title=employee.role_title)
            for user, employee in self.users.list_staff()
        ]

    async def create(self, payload: schemas.ProjectCreatePayload) -> dict:
        if self.projects.get_by_code(payload.project_code):
            raise ConflictError(DUPLICATE_CODE)

        electrical = self._resolve_lead(payload.project_lead_electrical_user_id, payload.project_lead_electrical)
        mechanical = self._resolve_lead(payload.project_lead_mechanical_user_id, payload.project_lead_mechanical)
        bim = self._resolve_lead(payload.project_lead_bim_user_id, payload.project_lead_bim)

        project = models.Project(
            project_name=payload.project_name,
            project_code=payload.project_code,
            client_organization=payload.client_customer,
            # The single legacy project_lead column keeps the primary (electrical) lead.
            project_lead=_primary_lead_name(electrical, mechanical, bim),
            start_date=payload.target_start_date,
            project_lead_electrical=electrical[0],
            project_lead_mechanical=mechanical[0],
            project_lead_bim=bim[0],
            project_lead_electrical_user_id=electrical[1],
            project_lead_mechanical_user_id=mechanical[1],
            project_lead_bim_user_id=bim[1],
            sharepoint_disciplines=json.dumps(payload.sharepoint_disciplines)
            if payload.sharepoint_disciplines
            else None,
            contract_value=payload.total_contract_value,
            contract_currency=payload.contract_currency,
            governance_threshold_pct=payload.alert_override_threshold_pct,
            target_effort_hours=payload.target_effort_hours,
        )
        try:
            self.projects.add(project)
            self.db.flush()
            self._sync_lead_assignments(project, payload)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(DUPLICATE_CODE) from exc
        self.db.refresh(project)

        data = self._outs([project], None)[0]
        data.update(
            await self._provision(project) if payload.sharepoint_disciplines else _sharepoint_result("not_requested")
        )
        return data

    def list_for(self, user: models.User, include_archived: bool = False) -> list[dict]:
        """Archived projects are listed only for the BU Head, and only on request."""
        projects = self.projects.list(
            visible_project_ids(self.db, user), include_archived=include_archived and user.role == Role.BU_HEAD
        )
        return self._outs(projects, user)

    def get_for(self, user: models.User, project_id: int) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        if not user_can_access_project(self.db, user, project):
            raise ForbiddenError(NO_PROJECT_ACCESS)
        return self._outs([project], user)[0]

    def _outs(self, projects: list[models.Project], user: models.User | None) -> list[dict]:
        """ProjectOut data: each lead slot's dates and % from the lead bookings, and the caller's
        role on each project (`my_role`: what the pages show). Four queries for any number of projects."""
        roles = project_roles(self.db, user) if user is not None and user.role != Role.BU_HEAD else None
        assignments: dict[tuple[int, int], models.ResourceBooking] = {}
        for booking in self.bookings.lead_assignments([p.id for p in projects]):
            assignments[(booking.project_id, booking.employee_id)] = booking
        lead_user_ids = {getattr(p, id_col) for p in projects for _, id_col in _LEAD_SLOTS} - {None}
        employee_of = self.users.employee_ids(lead_user_ids) if lead_user_ids else {}
        out = []
        for project in projects:
            data = schemas.ProjectOut.model_validate(project).model_dump()
            data["my_role"] = Role.BU_HEAD if roles is None else roles.get(project.id)
            for slot, (_, id_col) in zip(schemas.LEAD_SLOTS, _LEAD_SLOTS, strict=True):
                booking = assignments.get((project.id, employee_of.get(getattr(project, id_col))))
                if booking is not None:
                    data[f"project_lead_{slot}_start_date"] = booking.start_date
                    data[f"project_lead_{slot}_end_date"] = booking.end_date
                    data[f"project_lead_{slot}_utilization_pct"] = booking.utilization_rate
            out.append(data)
        return out

    def _sync_lead_assignments(self, project: models.Project, payload: schemas.ProjectFields) -> None:
        """The lead bookings mirror the lead slots, rebuilt on every save. Each holds the lead's
        capacity for the period (same date-aware 100% cap as engineer bookings), is approved from
        the start, and lists the lead among the project's people for WBS assignment."""
        self.bookings.delete_lead_assignments(project.id)
        self.db.flush()
        now = datetime.now(UTC)
        seen: set[int] = set()
        for slot in schemas.LEAD_SLOTS:
            assignment = payload.lead_assignment(slot)
            if assignment.user_id is None:
                continue  # no lead, or a name-only legacy lead without an account
            employee_id = self.users.get_staff(assignment.user_id).employee_id
            name = getattr(project, f"project_lead_{slot}")
            if employee_id in seen:
                raise BadRequestError(f"{name} can't hold two lead roles on one project.")
            seen.add(employee_id)
            if self.bookings.has_booking(project.id, employee_id, ENGINEER):
                raise ConflictError(
                    f"{name} is booked as an engineer on this project. Remove that booking before making them a lead."
                )
            pct, start, end = assignment.utilization_pct, assignment.start_date, assignment.end_date
            over = over_capacity_message(self.db, name, employee_id, pct, start, end)
            if over:
                raise BadRequestError(over)
            self.db.add(
                models.ResourceBooking(
                    project_id=project.id,
                    employee_id=employee_id,
                    role=LEAD,
                    planned_hours=planned_hours(start, end, pct),
                    utilization_rate=pct,
                    start_date=start,
                    end_date=end,
                    approval_status="approved",
                    approved_at=now,
                )
            )
            self.db.flush()  # the next slot's capacity check must see this one

    def update(self, user: models.User, project_id: int, payload: schemas.ProjectUpdatePayload) -> dict:
        """Edit a project. Every changed field is audited (before -> after); a replaced
        Lead's WBS nodes move to their successor so the old Lead loses access; and the
        timesheet lock is re-checked both ways (a raised target can lift an automatic
        lock, a lowered one can lock). SharePoint folders are not renamed."""
        project = self._project(project_id)
        if project.archived_at is not None:
            raise ConflictError(ARCHIVED_READ_ONLY)
        if payload.project_code != project.project_code and self.projects.get_by_code(payload.project_code):
            raise ConflictError(DUPLICATE_CODE)
        if payload.contract_currency != project.contract_currency and not payload.confirm_currency_change:
            raise ConflictError(CURRENCY_CHANGE)
        leads = [
            self._resolve_lead(getattr(payload, id_col), getattr(payload, name_col)) for name_col, id_col in _LEAD_SLOTS
        ]
        before = {field: getattr(project, field) for field in _AUDITED_FIELDS}
        old_lead_ids = [getattr(project, id_col) for _, id_col in _LEAD_SLOTS]

        project.project_name = payload.project_name
        project.project_code = payload.project_code
        project.client_organization = payload.client_customer
        project.start_date = payload.target_start_date
        project.contract_value = payload.total_contract_value
        project.contract_currency = payload.contract_currency
        project.target_effort_hours = payload.target_effort_hours
        project.governance_threshold_pct = payload.alert_override_threshold_pct
        for (name_col, id_col), (name, lead_id) in zip(_LEAD_SLOTS, leads, strict=True):
            setattr(project, name_col, name)
            setattr(project, id_col, lead_id)
        project.project_lead = _primary_lead_name(*leads)

        new_lead_ids = {lead_id for _, lead_id in leads if lead_id}
        moved = sum(
            self.projects.reassign_lead_nodes(project.id, old_id, new_id, name)
            for old_id, (name, new_id) in zip(old_lead_ids, leads, strict=True)
            if old_id and new_id and old_id != new_id and old_id not in new_lead_ids
        )
        changes = [
            f"{label}: {_audit_text(before[field])} -> {_audit_text(getattr(project, field))}"
            for field, label in _AUDITED_FIELDS.items()
            if before[field] != getattr(project, field)
        ]
        if moved:
            changes.append(f"{moved} WBS node(s) moved to the new lead")
        actor = user.full_name or user.username
        if changes:
            self.db.add(
                models.GovernanceAction(
                    project_id=project.id, action="edit_project", comments="; ".join(changes), created_by=actor
                )
            )
        self.monitor.evaluate(project, baseline_raised_by_bu_head=True)  # target may have moved: lock or unlock
        self._notify_lead_changes(project, set(filter(None, old_lead_ids)), new_lead_ids, actor)
        try:
            self._sync_lead_assignments(project, payload)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(DUPLICATE_CODE) from exc
        self.db.refresh(project)
        return {**self._outs([project], user)[0], "reassigned_nodes": moved}

    def _notify_lead_changes(self, project: models.Project, old_ids: set[int], new_ids: set[int], actor: str) -> None:
        name = project.project_name
        notify.notify_users(
            self.db, old_ids - new_ids, Role.ENGINEER, notify.PROJECT_LEAD_REMOVED,
            "No longer a project lead", f"You are no longer a lead on '{name}'.", project.id, actor,
        )  # fmt: skip
        notify.notify_users(
            self.db, new_ids - old_ids, Role.ENGINEER, notify.PROJECT_LEAD_ASSIGNED,
            "New project", f"You are now a lead on '{name}'.", project.id, actor,
        )  # fmt: skip

    def delete(self, project_id: int) -> dict:
        """Delete a project created by mistake. A project with any recorded work
        or history is archived instead, so its audit log survives. The SharePoint
        folder is kept."""
        project = self._project(project_id)
        if project.archived_at is not None:
            raise ConflictError(ARCHIVED_READ_ONLY)
        if self.projects.has_history(project_id):
            raise ConflictError(HAS_HISTORY)
        self.projects.delete_with_children(project)
        self.db.commit()
        return {"ok": True, "deleted_project_id": project_id}

    def archive(self, user: models.User, project_id: int, comments: str | None) -> models.Project:
        """Close a project: read-only, hidden from Leads and Engineers, out of the
        allocation cap and governance. Active tracking sessions are ended (their
        time banked) and a pending extension request is cancelled."""
        project = self._project(project_id)
        if project.archived_at is not None:
            raise ConflictError("This project is already archived.")
        now = datetime.now(UTC)
        actor = user.full_name or user.username
        with lifecycle_writes(self.db, project.id):
            project.archived_at = now
            for session in self.projects.active_sessions(project_id):
                end_session(self.db, session, now, PROJECT_ARCHIVED)
            for request in self.projects.pending_extension_requests(project_id):
                request.status = project.extension_status = EXTENSION_CANCELLED
                request.decided_by, request.decided_at = actor, now
                request.decision_comments = "Closed automatically: project archived."
            self.db.add(
                models.GovernanceAction(project_id=project.id, action="archive", comments=comments, created_by=actor)
            )
            notify.notify_project_leads(
                self.db,
                project,
                notify.PROJECT_ARCHIVED,
                "Project archived",
                f"'{project.project_name}' was archived by the BU Head. It is read-only and no longer listed for you.",
                actor,
            )
            self.db.commit()
        return project

    def unarchive(self, user: models.User, project_id: int, comments: str | None) -> models.Project:
        """Reopen a project exactly as it was, including its timesheet lock."""
        project = self._project(project_id)
        if project.archived_at is None:
            raise ConflictError("This project is not archived.")
        actor = user.full_name or user.username
        with lifecycle_writes(self.db, project.id):
            project.archived_at = None
            self.db.add(
                models.GovernanceAction(project_id=project.id, action="unarchive", comments=comments, created_by=actor)
            )
            notify.notify_project_leads(
                self.db,
                project,
                notify.PROJECT_UNARCHIVED,
                "Project reopened",
                f"'{project.project_name}' was reopened by the BU Head.",
                actor,
            )
            self.db.commit()
        return project

    def _project(self, project_id: int) -> models.Project:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        return project

    def _resolve_lead(self, user_id: int | None, display_name: str | None) -> tuple[str | None, int | None]:
        """(display name, lead user id); (None, None) when the discipline has no lead.
        With an id, the name comes from the real account."""
        if user_id is None:
            return display_name, None
        lead = self.users.get_staff(user_id)
        if not lead:
            raise BadRequestError("The selected lead must be an active account with an employee record.")
        return lead.full_name or lead.username, lead.id

    async def _provision(self, project: models.Project) -> dict:
        """Create the SharePoint folders. Failure never undoes the project; it is reported instead."""
        try:
            url = await self.storage.provision_project(project)
        except SharePointError as exc:
            logger.error("SharePoint provisioning failed for project %s: %s", project.project_code, exc)
            return _sharepoint_result("failed", error=str(exc))
        except Exception as exc:
            logger.exception("Unexpected SharePoint error for project %s", project.project_code)
            return _sharepoint_result("error", error=f"Unexpected error: {exc}")
        project.sharepoint_site_url = url
        self.db.commit()
        return _sharepoint_result("provisioned", url=url)


def _primary_lead_name(*leads: tuple[str | None, int | None]) -> str:
    """The legacy single `project_lead` column: the first discipline that has a lead."""
    return next(name for name, _ in leads if name)


def _audit_text(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _sharepoint_result(status: str, *, url: str | None = None, error: str | None = None) -> dict:
    result = {"sharepoint_status": status, "sharepoint_site_url": url}
    if error is not None:
        result["sharepoint_error"] = error
    return result
