"""Project Work Summary: per-lead oversight and per-engineer contribution."""

from collections import defaultdict

import models
from app.core.errors import NotFoundError
from app.domain.timesheets import entry_total
from app.repositories.projects import ProjectRepository
from app.repositories.work import WorkRepository

# KNOWN (roadmap 5.3): completion uses the legacy "Completed" status only, and
# engineer progress uses legacy status names; fixed with status normalization.
LEGACY_COMPLETED = "Completed"


def _stats():
    return {"total": 0, "completed": 0}


class WorkSummaryService:
    def __init__(self, projects: ProjectRepository, work: WorkRepository):
        self.projects = projects
        self.work = work

    def summary(self, project_id: int) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError("Project not found.")

        nodes = self.work.nodes_for_project(project_id, order_by_code=True)
        entries = self.work.entries_for_project(project_id)
        node_by_id = {node.id: node for node in nodes}

        phase_stats = defaultdict(_stats)
        lead_phases = defaultdict(set)
        lead_phase_stats = defaultdict(lambda: defaultdict(_stats))
        lead_nodes = defaultdict(int)
        eng_tasks = defaultdict(list)
        for node in nodes:
            completed = node.deliverable_status == LEGACY_COMPLETED
            if node.phase:
                phase_stats[node.phase]["total"] += 1
                phase_stats[node.phase]["completed"] += int(completed)
            if node.assigned_lead:
                lead_phases[node.assigned_lead].add(node.phase or "")
                lead_nodes[node.assigned_lead] += 1
                if node.phase:
                    lead_phase_stats[node.assigned_lead][node.phase]["total"] += 1
                    lead_phase_stats[node.assigned_lead][node.phase]["completed"] += int(completed)
            if node.assigned_engineer_id:
                eng_tasks[node.assigned_engineer_id].append(node)

        eng_logged = defaultdict(float)
        eng_approved = defaultdict(float)
        eng_pending = defaultdict(float)
        lead_logged = defaultdict(float)
        lead_approved = defaultdict(float)
        lead_pending_entries = defaultdict(int)
        task_eng_approved = defaultdict(float)
        for entry in entries:
            total = entry_total(entry)
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

        engineer_ids = sorted(eng_tasks)
        employees = self.work.employees_by_ids(engineer_ids)

        leads_out = []
        for lead_name in sorted(lead_nodes):
            phases = sorted(phase for phase in lead_phases[lead_name] if phase)
            leads_out.append(
                {
                    "name": lead_name,
                    "phases": phases,
                    "nodes_managed": lead_nodes[lead_name],
                    "phase_completion": {phase: dict(lead_phase_stats[lead_name][phase]) for phase in phases},
                    "approved_hours": round(lead_approved[lead_name], 2),
                    "logged_hours": round(lead_logged[lead_name], 2),
                    "pending_approvals": lead_pending_entries[lead_name],
                }
            )

        engineers_out = []
        for engineer_id in engineer_ids:
            employee = employees.get(engineer_id)
            if employee is None:
                continue
            tasks = sorted(eng_tasks[engineer_id], key=lambda task: str(task.wbs_code or ""))
            engineers_out.append(
                {
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
                    "progress_status": _legacy_progress_status(tasks),
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
                }
            )

        return {
            "project": _project_output(project),
            "leads": leads_out,
            "engineers": engineers_out,
            "phase_completion": dict(phase_stats),
            "summary": {
                "total_nodes": len(nodes),
                "completed_nodes": sum(1 for node in nodes if node.deliverable_status == LEGACY_COMPLETED),
                "scheduled_hours": sum(node.estimated_hours or 0 for node in nodes),
                "approved_hours": round(sum(eng_approved.values()), 2),
                "logged_hours": round(sum(eng_logged.values()), 2),
                "pending_hours": round(sum(eng_pending.values()), 2),
                "pending_entries": sum(lead_pending_entries.values()),
            },
        }


def _legacy_progress_status(tasks: list[models.WbsNode]) -> str:
    statuses = {task.deliverable_status for task in tasks}
    if "In Progress" in statuses:
        return "In Progress"
    if "Not Started" in statuses:
        return "Not Started"
    if statuses == {LEGACY_COMPLETED}:
        return LEGACY_COMPLETED
    return "—"


def _project_output(project: models.Project) -> dict:
    return {
        "id": project.id,
        "project_name": project.project_name,
        "project_code": project.project_code,
        "client_organization": project.client_organization,
        "project_lead": project.project_lead,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "target_end_date": project.target_end_date.isoformat() if project.target_end_date else None,
    }
