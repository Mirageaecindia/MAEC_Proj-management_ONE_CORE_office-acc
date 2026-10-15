"""wbs task name 500: room for the WBS node sheets' longest step (249 characters)

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only wider: every existing name fits. time_log_entries keeps a deleted subtask's name.
    with op.batch_alter_table("wbs_nodes", schema=None) as batch_op:
        batch_op.alter_column(
            "task_name", existing_type=sa.String(length=240), type_=sa.String(length=500), existing_nullable=False
        )
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.alter_column(
            "task_name", existing_type=sa.String(length=255), type_=sa.String(length=500), existing_nullable=True
        )


def downgrade() -> None:
    # Fails on PostgreSQL once a longer name is stored (the DD Major Services Routing step is 249).
    with op.batch_alter_table("time_log_entries", schema=None) as batch_op:
        batch_op.alter_column(
            "task_name", existing_type=sa.String(length=500), type_=sa.String(length=255), existing_nullable=True
        )
    with op.batch_alter_table("wbs_nodes", schema=None) as batch_op:
        batch_op.alter_column(
            "task_name", existing_type=sa.String(length=500), type_=sa.String(length=240), existing_nullable=False
        )
