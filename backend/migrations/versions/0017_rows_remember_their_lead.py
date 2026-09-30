"""rows remember their lead: deleting a subtask does not change who approves its hours

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Set when the subtask is deleted, next to task_name: the task's lead keeps reviewing the
    # day rows (with the usual fallback to the BU Head when their period is over), instead of
    # every deletion quietly moving approvals to the BU Head.
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("task_lead_user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.drop_column("task_lead_user_id")
