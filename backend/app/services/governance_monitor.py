"""Keeps a project's governance state in step with its logged hours.

Usage is approved hours only. Call `evaluate` (or `enforce_governance` from
main.py) after anything that changes approved hours (a Lead approving or
rejecting rows or weeks, edits to rows) or the baseline. Each level is acted on once, when it
is first reached:
- WARNING   -> notify the BU Head and the project's Leads;
- HARD_STOP -> lock timesheets automatically and notify them.
Dropping back (e.g. after an approved extension raises the baseline) re-arms
the alerts. Because only a *rise* into HARD_STOP locks, a BU Head who resumes
a project manually is not overridden by the next logged hour.
"""

from sqlalchemy.orm import Session

import models
from app.core.roles import Role
from app.domain.governance import (
    HARD_STOP,
    LEVEL_RANK,
    LOCK_AUTO,
    NORMAL,
    WARNING,
    GovernanceReading,
    read_governance,
)
from app.repositories.work import WorkRepository
from app.services import notifications as notify

SYSTEM_ACTOR = "System"


class GovernanceMonitor:
    def __init__(self, db: Session, work: WorkRepository):
        self.db = db
        self.work = work

    def reading(self, project: models.Project) -> GovernanceReading:
        return read_governance(
            self.work.approved_hours(project.id),
            project.target_effort_hours,
            project.extension_approved_hours,
            project.governance_threshold_pct,
        )

    def evaluate(self, project: models.Project) -> GovernanceReading:
        """Apply alerts/auto-lock for a level change. The caller commits."""
        reading = self.reading(project)
        previous = project.governance_alert_level or NORMAL
        if reading.level == previous:
            return reading
        project.governance_alert_level = reading.level
        if LEVEL_RANK[reading.level] > LEVEL_RANK[previous]:
            if reading.level == HARD_STOP:
                self._auto_lock(project, reading)
            elif reading.level == WARNING:
                self._notify(
                    project, notify.THRESHOLD_WARNING, "Alert threshold reached", _usage_text(project, reading)
                )
        return reading

    def _auto_lock(self, project: models.Project, reading: GovernanceReading) -> None:
        if not project.timesheets_soft_locked:
            project.timesheets_soft_locked = True
            project.lock_reason = LOCK_AUTO
            self.db.add(
                models.GovernanceAction(
                    project_id=project.id,
                    action="auto_lock",
                    consumption_pct=reading.consumption_pct,
                    threshold_pct=project.governance_threshold_pct,
                    consumption_hours=reading.approved_hours,
                    comments="Timesheets locked automatically: 100% of the baseline was reached.",
                    created_by=SYSTEM_ACTOR,
                )
            )
        self._notify(
            project,
            notify.EXECUTION_LOCKED,
            "Timesheets locked: baseline reached",
            f"{_usage_text(project, reading)} Timesheets are locked until the BU Head approves an extension "
            "or resumes execution.",
        )

    def _notify(self, project: models.Project, kind: str, title: str, message: str) -> None:
        notify.notify_role(self.db, Role.BU_HEAD, kind, title, message, project.id, SYSTEM_ACTOR)
        notify.notify_project_leads(self.db, project, kind, title, message, SYSTEM_ACTOR)


def _usage_text(project: models.Project, reading: GovernanceReading) -> str:
    threshold = project.governance_threshold_pct
    threshold_text = f"; alert threshold {threshold:g}%" if threshold is not None else ""
    return (
        f"'{project.project_name}': {reading.approved_hours:g} of {reading.baseline_hours:g} baseline hours "
        f"approved ({reading.consumption_pct:g}%{threshold_text})."
    )


def enforce_governance(db: Session, project_id: int) -> None:
    """Re-evaluate a project after its approved hours may have changed (Lead/Engineer code in main.py)."""
    project = db.get(models.Project, project_id)
    if project is None:
        return
    GovernanceMonitor(db, WorkRepository(db)).evaluate(project)
    db.commit()
