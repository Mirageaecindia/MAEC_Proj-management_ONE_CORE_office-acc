"""audit events: who did what and when, kept for AUDIT_RETENTION_DAYS

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new table, empty: the log starts at deployment. Nothing existing changes.
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(length=150), nullable=True),
        sa.Column("user_role", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("project_name", sa.String(length=240), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_events_at"), ["at"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_category"), ["category"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_events_user_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_project_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_category"))
        batch_op.drop_index(batch_op.f("ix_audit_events_at"))
    op.drop_table("audit_events")
