"""team members: a lead's picked people per project, for Assign Engineer

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table: the lead's team for a project. Nothing existing changes.
    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("lead_user_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "lead_user_id", "employee_id", name="uq_team_member"),
    )
    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_team_members_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_team_members_lead_user_id"), ["lead_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_team_members_project_id"), ["project_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_team_members_project_id"))
        batch_op.drop_index(batch_op.f("ix_team_members_lead_user_id"))
        batch_op.drop_index(batch_op.f("ix_team_members_id"))
    op.drop_table("team_members")
