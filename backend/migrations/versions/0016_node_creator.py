"""node creator: who created a WBS task or subtask

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An engineer may delete only the subtasks they created themselves, not ones the lead
    # planned for them. Nodes created before this have no creator: only the lead deletes them.
    with op.batch_alter_table("wbs_nodes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("wbs_nodes", schema=None) as batch_op:
        batch_op.drop_column("created_by_user_id")
