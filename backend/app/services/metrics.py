"""Governance figures for one project: consumption, threshold status, SPI,
budget burn, per-discipline breakdown and the monthly chart.

Every figure is derived from stored rows (wbs_nodes, time_log_entries,
employees, projects). `executive_dashboard_data` is also imported by the
Lead extension-request code in main.py to snapshot figures into the audit log.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

import models
from app.domain.calendar import distribute_hours_over_months, month_key, month_label
from app.domain.timesheets import entry_total
from app.repositories.work import WorkRepository

APPROVED = "approved"
PENDING_REVIEW = "pending_review"
UNASSIGNED = "Unassigned"


class ProjectMetricsService:
    def __init__(self, work: WorkRepository):
        self.work = work

    def dashboard_data(self, project: models.Project) -> dict:
        nodes = self.work.nodes_for_project(project.id)
        entries = self.work.entries_for_project(project.id)
        totals = {entry.id: entry_total(entry) for entry in entries}

        scheduled_hours = sum(node.estimated_hours or 0 for node in nodes)
        logged_hours = sum(totals.values())
        approved_hours = sum(totals[e.id] for e in entries if e.approval_status == APPROVED)
        pending = [e for e in entries if e.approval_status == PENDING_REVIEW]
        pending_hours = sum(totals[e.id] for e in pending)
        consumption_pct = round(logged_hours / scheduled_hours * 100, 1) if scheduled_hours else 0.0

        engineer_ids = sorted({node.assigned_engineer_id for node in nodes if node.assigned_engineer_id})
        employees = self.work.employees_by_ids(engineer_ids)

        threshold = project.governance_threshold_pct
        disciplines_out, exceptions = self._discipline_breakdown(
            nodes, entries, totals, engineer_ids, employees, threshold
        )

        max_discipline = max(disciplines_out, key=lambda d: d["consumption_pct"], default=None)
        max_pct = max_discipline["consumption_pct"] if max_discipline else consumption_pct
        over_threshold = threshold is not None and (
            bool(exceptions) or (max_discipline is not None and max_pct > threshold)
        )

        currency = project.contract_currency or "USD"
        contract_value = float(project.contract_value or 0)
        budget_consumed = (
            round(contract_value * (logged_hours / scheduled_hours), 2) if scheduled_hours and contract_value else 0.0
        )
        budget_pct = round(budget_consumed / contract_value * 100, 1) if contract_value else 0.0

        exceeded_disciplines = {d["name"] for d in disciplines_out if d["exceeded"]}

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
                "pending_entries": len(pending),
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
                "status": "exceeded" if over_threshold else "normal",
                "threshold_pct": threshold,
                "consumption_pct": consumption_pct,
                "max_discipline_pct": max_pct,
                "max_discipline": max_discipline["name"] if max_discipline else None,
                "soft_locked": bool(project.timesheets_soft_locked),
            },
            "spi": self._spi(approved_hours, scheduled_hours),
            "disciplines": disciplines_out,
            "exceptions": exceptions,
            "monthly_data": self._monthly(nodes, entries, totals, employees, exceeded_disciplines),
        }

    @staticmethod
    def _discipline_breakdown(nodes, entries, totals, engineer_ids, employees, threshold):
        """Hours per engineer, rolled up by the engineer's discipline."""
        baseline = defaultdict(float)
        consumed = defaultdict(float)
        approved = defaultdict(float)
        pending = defaultdict(float)
        pending_entries = defaultdict(int)
        for node in nodes:
            if node.assigned_engineer_id:
                baseline[node.assigned_engineer_id] += node.estimated_hours or 0
        for entry in entries:
            total = totals[entry.id]
            consumed[entry.employee_id] += total
            if entry.approval_status == APPROVED:
                approved[entry.employee_id] += total
            elif entry.approval_status == PENDING_REVIEW:
                pending[entry.employee_id] += total
                pending_entries[entry.employee_id] += 1

        disciplines = defaultdict(
            lambda: {
                "baseline_hours": 0.0,
                "consumed_hours": 0.0,
                "approved_hours": 0.0,
                "pending_hours": 0.0,
                "pending_entries": 0,
                "engineer_count": 0,
            }
        )
        for engineer_id in engineer_ids:
            employee = employees.get(engineer_id)
            if employee is None:
                continue
            disc = disciplines[employee.discipline or UNASSIGNED]
            disc["baseline_hours"] += baseline.get(engineer_id, 0.0)
            disc["consumed_hours"] += consumed.get(engineer_id, 0.0)
            disc["approved_hours"] += approved.get(engineer_id, 0.0)
            disc["pending_hours"] += pending.get(engineer_id, 0.0)
            disc["pending_entries"] += pending_entries.get(engineer_id, 0)
            disc["engineer_count"] += 1

        disciplines_out, exceptions = [], []
        for name in sorted(disciplines):
            disc = disciplines[name]
            pct = round(disc["consumed_hours"] / disc["baseline_hours"] * 100, 1) if disc["baseline_hours"] else 0.0
            exceeded = threshold is not None and disc["baseline_hours"] > 0 and pct > threshold
            disciplines_out.append(
                {
                    "name": name,
                    "baseline_hours": round(disc["baseline_hours"], 1),
                    "consumed_hours": round(disc["consumed_hours"], 1),
                    "approved_hours": round(disc["approved_hours"], 1),
                    "pending_hours": round(disc["pending_hours"], 1),
                    "pending_entries": disc["pending_entries"],
                    "consumption_pct": pct,
                    "exceeded": exceeded,
                    "engineer_count": disc["engineer_count"],
                }
            )
            if exceeded:
                exceptions.append(
                    {
                        "discipline": name,
                        "consumption_pct": pct,
                        "threshold_pct": threshold,
                        "consumed_hours": round(disc["consumed_hours"], 1),
                        "baseline_hours": round(disc["baseline_hours"], 1),
                        "pending_hours": round(disc["pending_hours"], 1),
                        "pending_entries": disc["pending_entries"],
                    }
                )
        return disciplines_out, exceptions

    @staticmethod
    def _spi(approved_hours: float, scheduled_hours: float) -> dict:
        if not scheduled_hours:
            return {"value": None, "note": "No baseline planned hours for this project yet."}
        value = round(approved_hours / scheduled_hours, 2)
        if value >= 1.0:
            note = f"Earned hours ({approved_hours:g}) match or exceed the planned baseline ({scheduled_hours:g})."
        else:
            note = f"Behind plan — {approved_hours:g} earned of {scheduled_hours:g} planned baseline hours."
        return {"value": value, "note": note}

    @staticmethod
    def _monthly(nodes, entries, totals, employees, exceeded_disciplines) -> list[dict]:
        """Planned hours spread over each node's months vs logged hours per month,
        split by whether the engineer's discipline is over threshold."""
        planned = defaultdict(float)
        normal = defaultdict(float)
        exceeded = defaultdict(float)
        for node in nodes:
            if node.estimated_hours and node.estimated_hours > 0:
                end = node.target_due_date or node.end_date
                for key, hours in distribute_hours_over_months(
                    float(node.estimated_hours), node.start_date, end
                ).items():
                    planned[key] += hours
        for entry in entries:
            total = totals[entry.id]
            if total <= 0:
                continue
            employee = employees.get(entry.employee_id)
            discipline = employee.discipline if employee else UNASSIGNED
            bucket = exceeded if discipline in exceeded_disciplines else normal
            bucket[month_key(entry.week_start_date)] += total

        return [
            {
                "month": key,
                "month_label": month_label(key),
                "planned_baseline": round(planned.get(key, 0.0), 1),
                "normal_consumption": round(normal.get(key, 0.0), 1),
                "exceeded_threshold": round(exceeded.get(key, 0.0), 1),
            }
            for key in sorted(set(planned) | set(normal) | set(exceeded))
        ]


def executive_dashboard_data(db: Session, project: models.Project) -> dict:
    """Function form kept for the Lead extension-request code in main.py."""
    return ProjectMetricsService(WorkRepository(db)).dashboard_data(project)
