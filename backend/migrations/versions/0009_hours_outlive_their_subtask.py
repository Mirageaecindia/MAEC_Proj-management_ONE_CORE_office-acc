"""hours outlive their subtask: day rows keep the subtask's name when it is deleted

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Worked hours are never deleted with their subtask (decided 2026-09-29); the row
    # remembers the subtask's name once the WBS node is gone.
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("task_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.drop_column("task_name")
