"""drop hours corrections: the feature was removed by decision

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Decided 2026-09-30: hours stay on the subtask they were logged on (project totals and
    # pay are right either way). Rejected hours get a second look from the project's leads
    # instead, and switching subtasks became one step. The requests recorded here are dropped.
    op.drop_table("hours_corrections")


def downgrade() -> None:
    op.create_table(
        "hours_corrections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("from_task_id", sa.Integer(), nullable=False),
        sa.Column("to_task_id", sa.Integer(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=150), nullable=True),
        sa.Column("decided_by", sa.String(length=150), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("hours_corrections", schema=None) as batch_op:
        for column in ("id", "project_id", "employee_id", "status"):
            batch_op.create_index(batch_op.f(f"ix_hours_corrections_{column}"), [column], unique=False)
