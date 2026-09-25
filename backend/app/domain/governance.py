"""Project governance rules (BU Head decisions, 2026-09-25).

- Baseline = the BU Head's Target Effort Hours + approved extension hours.
- Levels, whole project: logged hours below the alert threshold -> NORMAL;
  at/above the threshold -> WARNING (alert only); at/above 100% of the
  baseline -> HARD_STOP (timesheets lock automatically).
"""

from dataclasses import dataclass

NORMAL = "normal"
WARNING = "warning"
HARD_STOP = "hard_stop"

LEVEL_RANK = {NORMAL: 0, WARNING: 1, HARD_STOP: 2}
HARD_STOP_PCT = 100.0

# Why timesheets are locked (projects.lock_reason).
LOCK_MANUAL = "manual"  # BU Head pressed "Stop the Execution"
LOCK_AUTO = "auto"  # 100% of the baseline was reached


@dataclass(frozen=True)
class GovernanceReading:
    baseline_hours: float
    logged_hours: float
    consumption_pct: float
    threshold_pct: float | None
    level: str

    @property
    def configured(self) -> bool:
        return self.baseline_hours > 0


def governance_baseline(target_effort_hours: float | None, extension_approved_hours: float | None) -> float:
    return float(target_effort_hours or 0) + float(extension_approved_hours or 0)


def governance_level(consumption_pct: float, threshold_pct: float | None, baseline_hours: float) -> str:
    if baseline_hours <= 0:
        return NORMAL  # no baseline configured: nothing to govern against
    if consumption_pct >= HARD_STOP_PCT:
        return HARD_STOP
    if threshold_pct is not None and consumption_pct >= threshold_pct:
        return WARNING
    return NORMAL


def read_governance(
    logged_hours: float,
    target_effort_hours: float | None,
    extension_approved_hours: float | None,
    threshold_pct: float | None,
) -> GovernanceReading:
    baseline = governance_baseline(target_effort_hours, extension_approved_hours)
    pct = round(logged_hours / baseline * 100, 1) if baseline > 0 else 0.0
    return GovernanceReading(
        baseline_hours=round(baseline, 2),
        logged_hours=round(logged_hours, 2),
        consumption_pct=pct,
        threshold_pct=threshold_pct,
        level=governance_level(pct, threshold_pct, baseline),
    )


def split_monthly_consumption(
    monthly_logged: dict[str, float], alert_hours: float | None
) -> dict[str, tuple[float, float]]:
    """month -> (normal, exceeded): hours logged after cumulative consumption
    passed the alert level (threshold x baseline) count as exceeded."""
    result, cumulative = {}, 0.0
    for key in sorted(monthly_logged):
        hours = monthly_logged[key]
        if alert_hours is None:
            result[key] = (hours, 0.0)
        else:
            normal = max(0.0, min(hours, alert_hours - cumulative))
            result[key] = (normal, hours - normal)
        cumulative += hours
    return result
