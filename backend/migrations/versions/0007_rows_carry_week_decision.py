"""rows carry the week decision: approval is per row (per task) from now on

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SAME_WEEK = """
    FROM weekly_hours_submissions AS w
    WHERE w.project_id = time_log_entries.project_id
      AND w.employee_id = time_log_entries.employee_id
      AND w.week_start_date = time_log_entries.week_start_date
      AND w.status = '{status}'
"""


def upgrade() -> None:
    # Until now a Lead could approve or reject a whole week without touching its rows.
    # Approval is per row from now on (app/services/hours_review.py), so each pending row
    # takes its week's decision; the week's status is then derived from its rows.
    for status in ("approved", "rejected"):
        same_week = _SAME_WEEK.format(status=status)
        op.execute(
            f"""
            UPDATE time_log_entries
            SET approval_status = '{status}',
                reviewed_by = (SELECT w.reviewed_by {same_week}),
                reviewed_at = (SELECT w.reviewed_at {same_week})
            WHERE approval_status = 'pending_review' AND EXISTS (SELECT 1 {same_week})
            """
        )


def downgrade() -> None:
    pass  # the week decisions are still on weekly_hours_submissions; nothing to undo
