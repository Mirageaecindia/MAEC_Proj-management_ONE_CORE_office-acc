"""Governance figures for one project: consumption, threshold status, SPI,
budget burn, per-discipline breakdown and the monthly chart.

Consumption and the governance level are APPROVED hours measured at project
level against the BU Head's baseline (target effort hours + approved
extensions); see app/domain/governance.py. An hour is approved when its row or
its engineer's week was approved (app/domain/timesheets.effective_status);
rejected hours never count. WBS planned hours drive SPI, the planned series of
the monthly chart and the (informational) per-discipline breakdown.

Every figure is derived from stored rows (wbs_nodes, time_log_entries,
employees, projects). `executive_dashboard_data` is also imported by the
Lead extension-request code in main.py to snapshot figures into the audit log.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

import models
from app.domain.calendar import distribute_hours_over_months, month_key, month_label
from app.domain.governance import NORMAL, read_governance, split_monthly_consumption
from app.domain.timesheets import APPROVED, PENDING_REVIEW, effective_status, entry_total
from app.repositories.work import WorkRepository

UNASSIGNED = "Unassigned"


class ProjectMetricsService:
    def __init__(self, work: WorkRepository):
        self.work = work

    def dashboard_data(self, project: models.Project) -> dict:
        nodes = self.work.nodes_for_project(project.id)
        entries = self.work.entries_for_project(project.id)
        totals = {entry.id: entry_total(entry) for entry in entries}
        weeks = self.work.week_statuses(project.id)
        statuses = {
            entry.id: effective_status(entry.approval_status, weeks.get((entry.employee_id, entry.week_start_date)))
            for entry in entries
        }

        scheduled_hours = sum(node.estimated_hours or 0 for node in nodes)
        approved_hours = sum(totals[e.id] for e in entries if statuses[e.id] == APPROVED)
        pending = [e for e in entries if statuses[e.id] == PENDING_REVIEW]
        pending_hours = sum(totals[e.id] for e in pending)
        logged_hours = approved_hours + pending_hours  # rejected hours excluded
        rejected_hours = sum(totals.values()) - logged_hours
        threshold = project.governance_threshold_pct
        target = float(project.target_effort_hours or 0)
        reading = read_governance(approved_hours, target, project.extension_approved_hours, threshold)

        engineer_ids = sorted({node.assigned_engineer_id for node in nodes if node.assigned_engineer_id})
        employees = self.work.employees_by_ids(engineer_ids)
        disciplines_out, exceptions = self._discipline_breakdown(
            nodes, entries, totals, statuses, engineer_ids, employees, threshold
        )
        max_discipline = max(disciplines_out, key=lambda d: d["consumption_pct"], default=None)

        currency = project.contract_currency or "USD"
        contract_value = float(project.contract_value or 0)
        # Budget burn is proportional to approved hours of the commercial target (no rate card yet).
        budget_consumed = round(contract_value * (approved_hours / target), 2) if target and contract_value else 0.0
        budget_pct = round(budget_consumed / contract_value * 100, 1) if contract_value else 0.0
        alert_hours = reading.baseline_hours * threshold / 100 if reading.configured and threshold is not None else None

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
                "baseline_hours": reading.baseline_hours,
                "target_effort_hours": target,
                "extension_approved_hours": float(project.extension_approved_hours or 0),
                "approved_hours": round(approved_hours, 2),
                "logged_hours": round(logged_hours, 2),
                "pending_hours": round(pending_hours, 2),
                "pending_entries": len(pending),
                "rejected_hours": round(rejected_hours, 2),
                "consumption_pct": reading.consumption_pct,
            },
            "commercial_budget_burn": {
                "currency": currency,
                "total": round(contract_value, 2),
                "consumed": budget_consumed,
                "remaining": round(contract_value - budget_consumed, 2),
                "percent": budget_pct,
            },
            "hours_consumption": {
                "hours": reading.approved_hours,
                "scheduled": reading.baseline_hours,
                "wbs_planned": scheduled_hours,
                "approved": round(approved_hours, 2),
                "pending": round(pending_hours, 2),
                "percent": reading.consumption_pct,
            },
            "governance_status": {
                # 'exceeded' = at/above the alert threshold (kept for existing clients); see `level`.
                "status": "normal" if reading.level == NORMAL else "exceeded",
                "level": reading.level,
                "configured": reading.configured,
                "threshold_pct": threshold,
                "consumption_pct": reading.consumption_pct,
                "baseline_hours": reading.baseline_hours,
                "approved_hours": reading.approved_hours,
                "wbs_exceeds_target": bool(target) and scheduled_hours > target,
                "max_discipline_pct": max_discipline["consumption_pct"] if max_discipline else reading.consumption_pct,
                "max_discipline": max_discipline["name"] if max_discipline else None,
                "soft_locked": bool(project.timesheets_soft_locked),
                "lock_reason": project.lock_reason if project.timesheets_soft_locked else None,
            },
            "spi": self._spi(approved_hours, scheduled_hours),
            "disciplines": disciplines_out,
            "exceptions": exceptions,
            "monthly_data": self._monthly(nodes, entries, totals, statuses, alert_hours),
        }

    @staticmethod
    def _discipline_breakdown(nodes, entries, totals, statuses, engineer_ids, employees, threshold):
        """Hours per engineer (approved + pending; rejected excluded), rolled up by discipline."""
        baseline = defaultdict(float)
        consumed = defaultdict(float)
        approved = defaultdict(float)
        pending = defaultdict(float)
        pending_entries = defaultdict(int)
        for node in nodes:
            if node.assigned_engineer_id:
                baseline[node.assigned_engineer_id] += node.estimated_hours or 0
        for entry in entries:
            total, status = totals[entry.id], statuses[entry.id]
            if status == APPROVED:
                approved[entry.employee_id] += total
                consumed[entry.employee_id] += total
            elif status == PENDING_REVIEW:
                pending[entry.employee_id] += total
                pending_entries[entry.employee_id] += 1
                consumed[entry.employee_id] += total

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
    def _monthly(nodes, entries, totals, statuses, alert_hours: float | None) -> list[dict]:
        """WBS planned hours spread over each node's months vs approved hours per
        month; approved hours beyond the project's alert level count as exceeded."""
        planned = defaultdict(float)
        logged = defaultdict(float)
        for node in nodes:
            if node.estimated_hours and node.estimated_hours > 0:
                end = node.target_due_date or node.end_date
                for key, hours in distribute_hours_over_months(
                    float(node.estimated_hours), node.start_date, end
                ).items():
                    planned[key] += hours
        for entry in entries:
            if totals[entry.id] > 0 and statuses[entry.id] == APPROVED:
                logged[month_key(entry.week_start_date)] += totals[entry.id]
        split = split_monthly_consumption(logged, alert_hours)

        return [
            {
                "month": key,
                "month_label": month_label(key),
                "planned_baseline": round(planned.get(key, 0.0), 1),
                "normal_consumption": round(split.get(key, (0.0, 0.0))[0], 1),
                "exceeded_threshold": round(split.get(key, (0.0, 0.0))[1], 1),
            }
            for key in sorted(set(planned) | set(logged))
        ]


def executive_dashboard_data(db: Session, project: models.Project) -> dict:
    """Function form kept for the Lead extension-request code in main.py."""
    return ProjectMetricsService(WorkRepository(db)).dashboard_data(project)
