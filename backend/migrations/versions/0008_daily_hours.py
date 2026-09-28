"""daily hours: one row per subtask, engineer and day; no weekly submissions

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Approval is per day from now on (decided 2026-09-28). The weekly rows and the week
    # submissions hold test data only, so they are dropped rather than split.
    op.drop_table("weekly_hours_submissions")
    op.drop_table("time_log_entries")
    op.create_table(
        "time_log_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("approval_status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by", sa.String(length=150), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "task_id", "employee_id", "work_date", name="uq_time_log_day"),
    )
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        for column in ("id", "project_id", "task_id", "employee_id", "work_date", "approval_status"):
            batch_op.create_index(batch_op.f(f"ix_time_log_entries_{column}"), [column], unique=False)


def downgrade() -> None:
    # Back to the weekly tables of the baseline (empty: daily rows can't be folded back).
    op.drop_table("time_log_entries")
    op.create_table(
        "time_log_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        *[
            sa.Column(f"{day}_hours", sa.Float(), nullable=False)
            for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        ],
        sa.Column("approval_status", sa.String(length=20), nullable=False),
        sa.Column("reviewed_by", sa.String(length=150), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "task_id", "employee_id", "week_start_date", name="uq_time_log_week"),
    )
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        for column in ("employee_id", "id", "project_id", "task_id", "week_start_date"):
            batch_op.create_index(batch_op.f(f"ix_time_log_entries_{column}"), [column], unique=False)
    op.create_table(
        "weekly_hours_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=150), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "employee_id", "week_start_date", name="uq_weekly_hours_submission"),
    )
    with op.batch_alter_table("weekly_hours_submissions", schema=None) as batch_op:
        for column in ("employee_id", "id", "project_id", "status", "week_start_date"):
            batch_op.create_index(batch_op.f(f"ix_weekly_hours_submissions_{column}"), [column], unique=False)
