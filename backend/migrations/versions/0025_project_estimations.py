"""project estimations: the BU Head's resourcing estimates, made before a project exists

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table, empty. Nothing existing changes.
    op.create_table(
        "project_estimations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("project_estimations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_project_estimations_id"), ["id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("project_estimations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_project_estimations_id"))
    op.drop_table("project_estimations")
