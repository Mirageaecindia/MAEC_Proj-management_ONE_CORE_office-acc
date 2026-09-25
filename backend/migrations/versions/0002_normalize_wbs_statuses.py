"""Normalize WBS statuses to the current flow names (TODO N8).

Old rows used "Not Started", "In Progress", "Blocked", "Completed" and
"Submitted for Review"; Work Summary counted only "Completed", so completion
showed 0% for current data. New writes are normalized by models.WbsNode.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE wbs_nodes SET deliverable_status = 'To Do' WHERE deliverable_status IN ('Not Started', 'Blocked')"
    )
    op.execute("UPDATE wbs_nodes SET deliverable_status = 'In-Progress' WHERE deliverable_status = 'In Progress'")
    op.execute(
        "UPDATE wbs_nodes SET deliverable_status = 'Submitted for Approval' "
        "WHERE deliverable_status = 'Submitted for Review'"
    )
    op.execute(
        "UPDATE wbs_nodes SET deliverable_status = 'Approved' "
        "WHERE deliverable_status = 'Completed' AND parent_id IS NULL"
    )
    op.execute(
        "UPDATE wbs_nodes SET deliverable_status = 'Done' "
        "WHERE deliverable_status = 'Completed' AND parent_id IS NOT NULL"
    )


def downgrade() -> None:
    pass  # the old names can't be restored (several mapped to one); nothing depends on them
